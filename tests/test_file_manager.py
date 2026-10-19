import os
import shutil
import struct
import tempfile
import unittest
import threading
import pytest
from copy import deepcopy
from contextlib import ExitStack
import zlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from webview.util import parse_file_type

from backend.managers.mgr_files import FileManager, LinkSyncResult, LocalAssetHandler, PathChecker
from backend.settings import settings
from backend.utils.tools import normalize_path_for_storage


class TestFileManager(unittest.TestCase):
    def _write_mod_about(self, mod_path: Path, package_id: str, name: str = "Test Mod"):
        about_dir = mod_path / "About"
        about_dir.mkdir(parents=True, exist_ok=True)
        (about_dir / "About.xml").write_text(
            f"<ModMetaData><name>{name}</name><packageId>{package_id}</packageId></ModMetaData>",
            encoding="utf-8",
        )

    def _write_png_with_bad_iccp_crc(self, path):
        buffer = BytesIO()
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(buffer, "PNG")
        data = buffer.getvalue()
        ihdr_end = 8 + 12 + struct.unpack(">I", data[8:12])[0]

        chunk_data = b"broken\x00\x00" + zlib.compress(b"not a real profile")
        chunk = struct.pack(">I", len(chunk_data)) + b"iCCP" + chunk_data + b"\x00\x00\x00\x00"
        path.write_bytes(data[:ihdr_end] + chunk + data[ihdr_end:])

    def test_windows_open_in_explorer_selects_file_with_spaces_as_quoted_command(self):
        path = r"C:\Users\Administrator\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Config\Mod_1541721856_AlphaAnimals_Mod.xml"

        with (
            patch("backend.managers.mgr_files.os.path.exists", return_value=True),
            patch("backend.managers.mgr_files.os.path.isfile", return_value=True),
            patch("backend.managers.mgr_files.platform.system", return_value="Windows"),
            patch("backend.managers.mgr_files.subprocess.Popen") as popen,
        ):
            FileManager.open_in_explorer(path)

        popen.assert_called_once_with(
            'explorer.exe /select,"C:\\Users\\Administrator\\AppData\\LocalLow\\Ludeon Studios\\RimWorld by Ludeon Studios\\Config\\Mod_1541721856_AlphaAnimals_Mod.xml"'
        )

    def test_webview_file_types_reject_missing_dot_after_star(self):
        with self.assertRaises(ValueError):
            parse_file_type("RimCrow Data Package (*rimcrowdata.zip)")

    def test_complex_import_filters_can_use_webview_without_zip_wildcard_downgrade(self):
        file_types = (
            "RimCrow Data Package (*.rimcrowdata.zip;*.rmmdata.zip;*.rmmdata)",
            "Load Order Files (*.xml;*.rws;*.rml)",
            "All Files (*.*)",
        )

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                return ["picked.rimcrowdata.zip"]

        self.assertTrue(FileManager._can_use_webview_file_types(file_types))
        with (
            patch("backend.managers.mgr_files.webview.windows", [FakeWindow()]),
            patch("backend.managers.mgr_files.os.path.exists", return_value=True),
            patch("backend.managers.mgr_files.FileManager._run_tk_dialog") as tk_dialog,
        ):
            selected = FileManager.select_file_dialog("C:\\", file_types)

        self.assertEqual(selected, "picked.rimcrowdata.zip")
        tk_dialog.assert_not_called()

    def test_thumbnail_generation_supports_common_preview_formats(self):
        for extension in ("png", "jpg", "jpeg", "webp", "gif", "bmp"):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as temp_dir:
                preview_path = Path(temp_dir) / f"Preview.{extension}"
                with Image.new("RGB", (128, 96), "red") as image:
                    image.save(preview_path)
                with patch("backend.managers.mgr_files.THUMBNAIL_CACHE_DIR", temp_dir):
                    target_path = LocalAssetHandler._ensure_thumbnail("test.mod", str(preview_path))
                self.assertTrue(target_path)
                with Image.open(target_path) as thumbnail:
                    self.assertEqual(thumbnail.format, "WEBP")
                    self.assertEqual(thumbnail.size, (64, 48))

    def test_thumbnail_generation_tolerates_broken_png_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            preview_path = temp_path / "Preview.png"
            thumbnail_dir = temp_path / "thumbnails"
            thumbnail_dir.mkdir()
            self._write_png_with_bad_iccp_crc(preview_path)

            with patch("backend.managers.mgr_files.THUMBNAIL_CACHE_DIR", str(thumbnail_dir)):
                target_path = LocalAssetHandler._ensure_thumbnail("test.mod", str(preview_path))

            self.assertTrue(target_path)
            self.assertTrue(os.path.isfile(target_path))
            with Image.open(target_path) as image:
                self.assertEqual(image.format, "WEBP")

    def test_copy_folders_with_progress_syncs_existing_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src = temp_path / "src"
            dst = temp_path / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "About").mkdir()
            (dst / "old.txt").write_text("old", encoding="utf-8")
            (src / "About" / "About.xml").write_text("<ModMetaData />", encoding="utf-8")

            cleanup_calls = []
            def fake_delete(path, force=False):
                cleanup_calls.append((Path(path).name, force))
                shutil.rmtree(path)
                return True

            with patch("backend.managers.mgr_files.delete_fs_path", side_effect=fake_delete):
                success, errors, total = FileManager.copy_folders_with_progress([
                    {"src": str(src), "dst": str(dst), "label": "Test Mod"}
                ])

            self.assertEqual(total, 1)
            self.assertEqual(errors, [])
            self.assertEqual(success, [str(dst)])
            self.assertTrue((dst / "About" / "About.xml").is_file())
            self.assertFalse((dst / "old.txt").exists())
            self.assertFalse((temp_path / "dst_1").exists())
            self.assertTrue(any(name.startswith("dst.__sync_backup_") and force for name, force in cleanup_calls))

    def test_copy_folders_with_progress_restores_existing_destination_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src = temp_path / "src"
            dst = temp_path / "dst"
            src.mkdir()
            dst.mkdir()
            self._write_mod_about(src, "test.mod")
            (dst / "old.txt").write_text("old", encoding="utf-8")

            real_move = shutil.move
            def fail_tmp_move(src_path, dst_path, *args, **kwargs):
                if ".__sync_tmp_" in str(src_path):
                    raise OSError("move failed")
                return real_move(src_path, dst_path, *args, **kwargs)

            with patch("backend.managers.mgr_files.shutil.move", side_effect=fail_tmp_move):
                success, errors, total = FileManager.copy_folders_with_progress([
                    {"src": str(src), "dst": str(dst), "label": "Test Mod"}
                ])

            self.assertEqual(total, 1)
            self.assertEqual(success, [])
            self.assertEqual(len(errors), 1)
            self.assertTrue((dst / "old.txt").is_file())
            self.assertFalse((dst / "About" / "About.xml").exists())
            self.assertFalse(list(temp_path.glob("dst.__sync_*")))

    def test_localize_complete_reports_size_check_paths(self):
        class ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self.target = target

            def start(self):
                self.target()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src = temp_path / "src"
            local_root = temp_path / "local"
            src.mkdir()
            local_root.mkdir()
            (src / "About").mkdir()
            (src / "About" / "About.xml").write_text("<ModMetaData />", encoding="utf-8")

            events = []
            with patch("backend.managers.mgr_files.threading.Thread", ImmediateThread), \
                 patch("backend.managers.mgr_files.EventBus.emit", side_effect=lambda name, data=None: events.append((name, data))), \
                 patch("backend.managers.mgr_files.EventBus.emit_progress"), \
                 patch("backend.managers.mgr_files.EventBus.resume"):
                FileManager.localize_workshop_mods([
                    {
                        "path": str(src),
                        "workshop_id": "123456",
                        "name": "Test Mod",
                        "package_id": "test.mod",
                    }
                ], str(local_root))

            complete_payloads = [payload for name, payload in events if name == "localize-complete"]
            self.assertEqual(len(complete_payloads), 1)
            payload = complete_payloads[0]
            expected_dst = local_root / "123456"
            expected_source = normalize_path_for_storage(str(src))
            expected_success = normalize_path_for_storage(str(expected_dst))
            self.assertEqual(payload["source_paths"], [expected_source])
            self.assertEqual(payload["success_paths"], [expected_success])
            self.assertEqual(payload["size_check_paths"], [expected_source, expected_success])

    def test_localize_syncs_existing_legacy_underscore_folder_for_same_package(self):
        class ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self.target = target

            def start(self):
                self.target()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src = temp_path / "src"
            local_root = temp_path / "local"
            legacy_dst = local_root / "_123456_"
            src.mkdir()
            local_root.mkdir()
            self._write_mod_about(src, "test.mod")
            self._write_mod_about(legacy_dst, "test.mod")

            events = []
            with patch("backend.managers.mgr_files.threading.Thread", ImmediateThread), \
                 patch("backend.managers.mgr_files.EventBus.emit", side_effect=lambda name, data=None: events.append((name, data))), \
                 patch("backend.managers.mgr_files.EventBus.emit_progress"), \
                 patch("backend.managers.mgr_files.EventBus.resume"):
                FileManager.localize_workshop_mods([
                    {
                        "path": str(src),
                        "workshop_id": "123456",
                        "name": "Test Mod",
                        "package_id": "test.mod",
                    }
                ], str(local_root))

            complete_payloads = [payload for name, payload in events if name == "localize-complete"]
            self.assertEqual(len(complete_payloads), 1)
            self.assertEqual(complete_payloads[0]["success_paths"], [normalize_path_for_storage(str(legacy_dst))])

    def test_localize_reports_same_folder_different_package_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src = temp_path / "src"
            local_root = temp_path / "local"
            existing_dst = local_root / "123456"
            src.mkdir()
            local_root.mkdir()
            self._write_mod_about(src, "target.mod")
            self._write_mod_about(existing_dst, "other.mod")

            result = FileManager.localize_workshop_mods([
                {
                    "path": str(src),
                    "path_hash": "hash-1",
                    "workshop_id": "123456",
                    "name": "Target Mod",
                    "package_id": "target.mod",
                }
            ], str(local_root))

            self.assertTrue(result["requires_conflict_action"])
            self.assertEqual(result["conflicts"][0]["target_folder"], "123456")
            self.assertEqual(result["conflicts"][0]["package_id"], "target.mod")
            self.assertEqual(result["conflicts"][0]["existing_package_id"], "other.mod")

    def test_localize_save_as_overwrites_legacy_underscore_folder_for_conflict(self):
        class ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self.target = target

            def start(self):
                self.target()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src = temp_path / "src"
            local_root = temp_path / "local"
            existing_dst = local_root / "123456"
            save_as_dst = local_root / "_123456_"
            src.mkdir()
            local_root.mkdir()
            self._write_mod_about(src, "target.mod")
            self._write_mod_about(existing_dst, "other.mod")
            self._write_mod_about(save_as_dst, "legacy.other")

            events = []
            with patch("backend.managers.mgr_files.threading.Thread", ImmediateThread), \
                 patch("backend.managers.mgr_files.EventBus.emit", side_effect=lambda name, data=None: events.append((name, data))), \
                 patch("backend.managers.mgr_files.EventBus.emit_progress"), \
                 patch("backend.managers.mgr_files.EventBus.resume"):
                FileManager.localize_workshop_mods([
                    {
                        "path": str(src),
                        "workshop_id": "123456",
                        "name": "Target Mod",
                        "package_id": "target.mod",
                    }
                ], str(local_root), conflict_action="save_as")

            complete_payloads = [payload for name, payload in events if name == "localize-complete"]
            self.assertEqual(len(complete_payloads), 1)
            self.assertEqual(complete_payloads[0]["success_paths"], [normalize_path_for_storage(str(save_as_dst))])
            self.assertIn("<packageId>target.mod</packageId>", (save_as_dst / "About" / "About.xml").read_text(encoding="utf-8"))

    def test_check_steam_path_accepts_macos_steam_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = Path(temp_dir) / "Steam"
            steam_exe = steam_root / "Steam.app" / "Contents" / "MacOS" / "steam_osx"
            steam_exe.parent.mkdir(parents=True, exist_ok=True)
            steam_exe.write_text("", encoding="utf-8")

            with patch("backend.managers.mgr_files.platform.system", return_value="Darwin"):
                result = PathChecker.check_steam_path(str(steam_root))

            self.assertTrue(result["pass"])
            self.assertIn("steam_osx", result["msg"])
            self.assertEqual(result["data"], str(steam_root))

    def test_check_steam_path_accepts_macos_app_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = Path(temp_dir) / "Steam"
            steam_app = steam_root / "Steam.app"
            steam_exe = steam_app / "Contents" / "MacOS" / "steam_osx"
            steam_exe.parent.mkdir(parents=True, exist_ok=True)
            steam_exe.write_text("", encoding="utf-8")

            with patch("backend.managers.mgr_files.platform.system", return_value="Darwin"):
                result = PathChecker.check_steam_path(str(steam_app))

            self.assertTrue(result["pass"])
            self.assertEqual(result["data"], str(steam_root))

    def test_check_steam_path_accepts_macos_steam_osx(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = Path(temp_dir) / "Steam"
            steam_exe = steam_root / "Steam.app" / "Contents" / "MacOS" / "steam_osx"
            steam_exe.parent.mkdir(parents=True, exist_ok=True)
            steam_exe.write_text("", encoding="utf-8")

            with patch("backend.managers.mgr_files.platform.system", return_value="Darwin"):
                result = PathChecker.check_steam_path(str(steam_exe))

            self.assertTrue(result["pass"])
            self.assertEqual(result["data"], str(steam_root))

    def test_check_steamcmd_path_accepts_unix_shell_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steamcmd_root = Path(temp_dir) / "steamcmd"
            steamcmd_exe = steamcmd_root / "steamcmd.sh"
            steamcmd_root.mkdir(parents=True, exist_ok=True)
            steamcmd_exe.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch("backend.managers.mgr_files.platform.system", return_value="Darwin"):
                result = PathChecker.check_steamcmd_path(str(steamcmd_root))

            self.assertTrue(result["pass"])
            self.assertIn("steamcmd.sh", result["msg"])

    def test_windows_junction_support_rejects_fat_file_systems(self):
        with (
            patch("backend.managers.mgr_files.platform.system", return_value="Windows"),
            patch.object(FileManager, "_get_windows_filesystem_type", return_value="exFAT"),
        ):
            self.assertFalse(FileManager._is_junction_supported(r"E:\steamcmd"))

        with (
            patch("backend.managers.mgr_files.platform.system", return_value="Windows"),
            patch.object(FileManager, "_get_windows_filesystem_type", return_value=""),
        ):
            self.assertTrue(FileManager._is_junction_supported(r"E:\steamcmd"))

    def test_sync_managed_links_stops_before_deleting_on_unsupported_filesystem(self):
        with (
            patch.object(FileManager, "_get_link_deployment_failure", return_value="请改用 NTFS"),
            patch.object(FileManager, "_remove_directory_link") as remove,
        ):
            result = FileManager.sync_managed_links("E:/Profile/Mods", ["E:/Workshop/1001"])
        self.assertFalse(result.ok)
        self.assertIn("NTFS", result.message)
        remove.assert_not_called()

    def test_sync_managed_links_allows_empty_deployment_on_exfat(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(FileManager, "_get_link_deployment_failure") as precheck:
                result = FileManager.sync_managed_links(root, [])
            self.assertTrue(result.ok)
            self.assertEqual(result.status, "noop")
            precheck.assert_not_called()

    def test_check_steamcmd_path_warns_when_windows_junction_is_unsupported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steamcmd_root = Path(temp_dir) / "steamcmd"
            steamcmd_exe = steamcmd_root / "steamcmd.exe"
            steamcmd_root.mkdir(parents=True)
            steamcmd_exe.write_text("", encoding="utf-8")

            with (
                patch("backend.managers.mgr_files.platform.system", return_value="Windows"),
                patch.object(FileManager, "_get_windows_filesystem_type", return_value="exFAT"),
            ):
                result = PathChecker.check_steamcmd_path(str(steamcmd_root))

            self.assertTrue(result["pass"])
            self.assertEqual(result["type"], "warn")
            self.assertIn("NTFS", result["msg"])

    def test_check_steamcmd_path_checks_download_directory_filesystem(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            steamcmd_root = Path(temp_dir) / "steamcmd"
            steamcmd_exe = steamcmd_root / "steamcmd.exe"
            steamcmd_root.mkdir(parents=True)
            steamcmd_exe.write_text("", encoding="utf-8")

            def filesystem_type(path):
                return "exFAT" if str(path).endswith(os.path.join("content", "294100")) else "NTFS"

            with (
                patch("backend.managers.mgr_files.platform.system", return_value="Windows"),
                patch.object(FileManager, "_get_windows_filesystem_type", side_effect=filesystem_type),
            ):
                result = PathChecker.check_steamcmd_path(str(steamcmd_root))

            self.assertTrue(result["pass"])
            self.assertEqual(result["type"], "warn")
            self.assertIn(str(steamcmd_root / "steamapps" / "workshop" / "content" / "294100"), result["msg"])

    def test_settings_update_preserves_old_config_when_steamcmd_link_sync_fails(self):
        original = deepcopy(settings.config)
        with (
            patch.object(settings, "config", deepcopy(original)),
            patch.object(FileManager, "sync_steamcmd_root_link", return_value=LinkSyncResult(False, "failed", "probe failed")),
            patch.object(settings, "save") as save,
        ):
            with self.assertRaisesRegex(RuntimeError, "probe failed"):
                settings.update_from_dict({"self_mods_path": "E:/probe/custom-mods"})
            self.assertEqual(settings.config, original)
            save.assert_not_called()

    def test_sync_steamcmd_root_link_uses_steamcmd_directory_when_default_storage_is_empty(self):
        with tempfile.TemporaryDirectory() as root:
            default, link = Path(root) / "mods", Path(root) / "downloads"
            with (
                patch("backend.managers.mgr_files.MODS_DIR", default),
                patch.object(FileManager, "_is_junction_supported", return_value=False),
                patch.object(FileManager, "_create_directory_link") as create,
            ):
                saved = []
                result = FileManager.sync_steamcmd_root_link(str(default), str(link), commit=saved.append)
            self.assertTrue(result.ok)
            self.assertEqual(saved, [str(link)])
            self.assertFalse(default.exists())
            self.assertTrue(link.is_dir())
            create.assert_not_called()

    def test_sync_steamcmd_root_link_does_not_replace_nonempty_or_custom_storage(self):
        with tempfile.TemporaryDirectory() as root:
            default, custom, link = (Path(root) / name for name in ("mods", "custom", "downloads"))
            default.mkdir()
            (default / "preserve").write_text("keep")
            with (
                patch("backend.managers.mgr_files.MODS_DIR", default),
                patch.object(FileManager, "_is_junction_supported", return_value=False),
            ):
                for storage in (default, custom):
                    self.assertFalse(FileManager.sync_steamcmd_root_link(str(storage), str(link)).ok)
            self.assertEqual((default / "preserve").read_text(), "keep")


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("name", ["弱运 游戏", "日本語 한국어", "emoji_😀", "%RIMCROW_PROBE% !test! (mod)"])
def test_native_links_preserve_unicode_and_literal_paths(tmp_path, full, name):
    source = tmp_path / "sources" / name
    source.mkdir(parents=True)
    (source / "sentinel").write_text("keep")
    root = tmp_path / "Mods"
    with patch.object(settings.config, "link_deployment_mode_full", full), patch.dict(os.environ, {"RIMCROW_PROBE": "WRONG_TARGET"}), patch("backend.managers.mgr_files.subprocess.run") as shell:
        result = FileManager.sync_managed_links(str(root), [str(source)])
        link = root / (FileManager.LINK_PREFIX + name)
        assert result.ok, result
        assert os.path.samefile(link, source)
        assert FileManager.sync_managed_links(str(root), [str(source)]).ok
        assert FileManager.sync_managed_links(str(root), []).ok
        assert not os.path.lexists(link)
        assert (source / "sentinel").read_text() == "keep"
        shell.assert_not_called()


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_managed_sync_never_removes_ordinary_prefix_entries(tmp_path, kind):
    root = tmp_path / "Mods"
    root.mkdir()
    entry = root / "_Link_manual"
    if kind == "directory":
        entry.mkdir()
        (entry / "sentinel").write_text("keep")
    else:
        entry.write_text("keep")
    result = FileManager.sync_managed_links(str(root), [])
    assert not result.ok
    assert entry.exists()
    with pytest.raises(OSError):
        FileManager._remove_directory_link(str(entry))
    assert entry.exists()


def test_deployment_collision_rejected_before_changing_links(tmp_path):
    a, b, old, root = (tmp_path / part for part in ("self/common", "workshop/common", "old", "Mods"))
    for folder in (a, b, old, root):
        folder.mkdir(parents=True)
    link = root / "_Link_old"
    FileManager._create_directory_link(str(old), str(link))
    result = FileManager.sync_managed_links(str(root), [str(a), str(b)])
    assert not result.ok and "common" in result.message
    assert os.path.samefile(link, old)


@pytest.mark.parametrize("full", [False, True])
def test_failed_link_delete_is_not_reported_as_success(tmp_path, full):
    source, root = tmp_path / "source", tmp_path / "Mods"
    source.mkdir(); root.mkdir()
    link = root / "_Link_old"
    FileManager._create_directory_link(str(source), str(link))
    with patch.object(settings.config, "link_deployment_mode_full", full), patch.object(FileManager, "_remove_directory_link", side_effect=PermissionError("locked")):
        result = FileManager.sync_managed_links(str(root), [])
    assert not result.ok and "locked" in result.message
    assert os.path.samefile(link, source)


def test_partial_creation_failure_restores_usable_links_and_removes_new_links(tmp_path):
    root, old, a, b = (tmp_path / part for part in ("Mods", "old", "a", "b"))
    for folder in (root, old, a, b): folder.mkdir()
    FileManager._create_directory_link(str(old), str(root / "_Link_old"))
    create = FileManager._create_directory_link
    def fail_after_create(source, destination):
        create(source, destination)
        if source == str(b): raise OSError("post-create failure")
    with patch.object(FileManager, "_create_directory_link", side_effect=fail_after_create):
        result = FileManager.sync_managed_links(str(root), [str(a), str(b)])
    assert not result.ok and not result.rollback_errors
    assert os.path.samefile(root / "_Link_old", old)
    assert not os.path.lexists(root / "_Link_a")
    assert not os.path.lexists(root / "_Link_b")


def test_dangling_link_repaired_without_restoring_bad_target(tmp_path):
    root, missing, good = (tmp_path / part for part in ("Mods", "missing", "good"))
    for folder in (root, missing, good): folder.mkdir()
    link = root / "_Link_good"
    FileManager._create_directory_link(str(missing), str(link))
    missing.rmdir()
    assert os.path.lexists(link) and not link.exists()
    result = FileManager.sync_managed_links(str(root), [str(good)])
    assert result.ok and os.path.samefile(link, good)


@pytest.mark.parametrize("source_inside", [True, False])
def test_runtime_deployment_rejects_overlapping_roots(tmp_path, source_inside):
    outer, inner = tmp_path / "outer", tmp_path / "outer/inner"
    inner.mkdir(parents=True)
    root, source = (outer, inner) if source_inside else (inner, outer)
    assert not FileManager.sync_managed_links(str(root), [str(source)]).ok


def test_root_migration_copies_verifies_and_commits_before_recycling_source(tmp_path):
    source, target = tmp_path / "downloads", tmp_path / "storage"
    source.mkdir()
    (source / "mod").mkdir()
    (source / "mod/file").write_bytes(b"preserve bytes")
    recycled, saved = [], []
    def recycle(path, force=False):
        assert saved and not force
        recycled.append(path)
        return True
    def commit(path):
        assert os.path.samefile(source, target)
        assert (target / "mod/file").read_bytes() == b"preserve bytes"
        saved.append(path)
    with patch("backend.managers.mgr_files.delete_fs_path", side_effect=recycle):
        result = FileManager.sync_steamcmd_root_link(str(target), str(source), commit=commit)
    assert result.ok, result
    assert saved == [str(target)] and len(recycled) == 2
    assert os.path.samefile(source, target)


@pytest.mark.parametrize("failure", ["copy", "verify", "create", "save"])
def test_root_migration_failure_preserves_original_data(tmp_path, failure):
    source, target = tmp_path / "downloads", tmp_path / "storage"
    source.mkdir()
    (source / "mod").write_bytes(b"original")
    commit = unittest.mock.Mock(side_effect=OSError("save failed") if failure == "save" else None)
    with ExitStack() as stack:
        if failure == "copy": stack.enter_context(patch("backend.managers.mgr_files.shutil.copytree", side_effect=OSError("copy failed")))
        if failure == "verify":
            manifest = FileManager._storage_manifest
            stack.enter_context(patch.object(FileManager, "_storage_manifest", side_effect=lambda root: {} if ".rimcrow-migration-" in root else manifest(root)))
        if failure == "create": stack.enter_context(patch.object(FileManager, "_create_directory_link", side_effect=OSError("create failed")))
        # 测试只检查清理请求，不向系统回收站写入临时测试副本。
        stack.enter_context(patch("backend.managers.mgr_files.delete_fs_path", return_value=True))
        result = FileManager.sync_steamcmd_root_link(str(target), str(source), commit=commit)
    assert not result.ok
    assert not FileManager.is_directory_link(str(source))
    assert (source / "mod").read_bytes() == b"original"
    if failure != "save": commit.assert_not_called()


@pytest.mark.parametrize("inverted", [False, True])
def test_root_migration_rejects_nested_storage_without_mutation(tmp_path, inverted):
    outer, inner = tmp_path / "downloads", tmp_path / "downloads/storage"
    inner.mkdir(parents=True)
    (outer / "sentinel").write_text("keep")
    source, target = (outer, inner) if not inverted else (inner, outer)
    result = FileManager.sync_steamcmd_root_link(str(target), str(source))
    assert not result.ok
    assert (outer / "sentinel").read_text() == "keep"
    assert inner.is_dir()


def test_migration_conflict_preserves_both_versions(tmp_path):
    source, target = tmp_path / "downloads", tmp_path / "storage"
    for root, content in ((source, "old"), (target, "new")):
        root.mkdir(); (root / "mod").write_text(content)
    result = FileManager.sync_steamcmd_root_link(str(target), str(source))
    assert not result.ok
    assert (source / "mod").read_text() == "old"
    assert (target / "mod").read_text() == "new"


def test_link_lock_identifies_same_physical_root(tmp_path):
    physical, alias = tmp_path / "Mods", tmp_path / "alias"
    physical.mkdir()
    FileManager._create_directory_link(str(physical), str(alias))
    assert FileManager.link_lock(str(physical)) is FileManager.link_lock(str(alias))


def test_settings_refuse_path_change_while_storage_in_use():
    ready, release = threading.Event(), threading.Event()
    def hold():
        with FileManager.storage_lock:
            ready.set()
            assert release.wait(5)
    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert ready.wait(5)
        original = deepcopy(settings.config)
        with pytest.raises(RuntimeError):
            settings.update_from_dict({"self_mods_path": "E:/probe/blocked"})
        assert settings.config == original
    finally:
        release.set(); worker.join(5)
    assert not worker.is_alive()


def test_shared_download_storage_root_still_migrates_old_data(tmp_path):
    old, target = tmp_path / "old", tmp_path / "downloads"
    old.mkdir()
    (old / "mod").write_bytes(b"keep")
    commit = unittest.mock.Mock()
    with patch("backend.managers.mgr_files.delete_fs_path", return_value=True):
        result = FileManager.sync_steamcmd_root_link(
            str(target), str(target), old_mods_path=str(old), move_old_data=True, commit=commit,
        )
    assert result.ok and result.status == "deployed"
    assert (target / "mod").read_bytes() == b"keep"
    assert not FileManager.is_directory_link(str(target))
    commit.assert_called_once_with(str(target))


def test_unchanged_paths_do_not_block_saving_other_settings():
    with patch.object(settings, "config", deepcopy(settings.config)), \
         patch.object(settings, "save") as save, \
         patch.object(FileManager, "storage_lock") as lock:
        settings.update_from_dict({
            "self_mods_path": settings.config.self_mods_path,
            "steamcmd_path": settings.config.steamcmd_path,
            "enable_auto_scan": not settings.config.enable_auto_scan,
        })
        lock.acquire.assert_not_called()
        save.assert_called_once_with()


def test_final_verification_rejects_creator_that_does_not_create_link(tmp_path):
    source, root = tmp_path / "source", tmp_path / "Mods"
    source.mkdir()
    with patch.object(FileManager, "_create_directory_link"):
        result = FileManager.sync_managed_links(str(root), [str(source)])
    assert not result.ok and not list(root.iterdir())


def test_failed_rollback_is_in_user_visible_message(tmp_path):
    root, old, source = (tmp_path / part for part in ("Mods", "old", "source"))
    for folder in (root, old, source): folder.mkdir()
    old_link = root / "_Link_old"
    FileManager._create_directory_link(str(old), str(old_link))
    with patch.object(FileManager, "_create_directory_link", side_effect=OSError("creation blocked")):
        result = FileManager.sync_managed_links(str(root), [str(source)])
    assert not result.ok and result.rollback_errors
    assert str(old_link) in result.message
    assert (old).is_dir() and source.is_dir()


def test_save_failure_restores_old_root_junction(tmp_path):
    old, target, link = (tmp_path / part for part in ("old", "new", "downloads"))
    old.mkdir(); target.mkdir()
    (old / "mod").write_bytes(b"original")
    FileManager._create_directory_link(str(old), str(link))
    with patch("backend.managers.mgr_files.delete_fs_path", return_value=True):
        result = FileManager.sync_steamcmd_root_link(
            str(target), str(link), old_mods_path=str(old), move_old_data=True,
            commit=unittest.mock.Mock(side_effect=OSError("save failed")),
        )
    assert not result.ok and not result.rollback_errors
    assert os.path.samefile(link, old)
    assert (link / "mod").read_bytes() == b"original"


def test_runtime_sync_serializes_workers_for_same_physical_root(tmp_path):
    root, source = tmp_path / "Mods", tmp_path / "source"
    source.mkdir()
    entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
    create = FileManager._create_directory_link
    results = []
    def slow_create(origin, destination):
        entered.set()
        assert release.wait(5)
        create(origin, destination)
    def sync(second=False):
        if second: second_started.set()
        results.append(FileManager.sync_managed_links(str(root), [str(source)]))
    first, second = threading.Thread(target=sync), threading.Thread(target=sync, args=(True,))
    with patch.object(FileManager, "_create_directory_link", side_effect=slow_create):
        first.start()
        try:
            assert entered.wait(5)
            second.start()
            assert second_started.wait(5)
            assert not results
        finally:
            release.set()
            first.join(5)
            if second.ident is not None: second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert len(results) == 2 and all(result.ok for result in results)
    assert os.path.samefile(root / "_Link_source", source)
