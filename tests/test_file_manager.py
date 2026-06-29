import os
import shutil
import struct
import tempfile
import unittest
import zlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.managers.mgr_files import FileManager, LocalAssetHandler
from backend.utils.tools import normalize_path_for_storage


class TestFileManager(unittest.TestCase):
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
            (src / "About").mkdir()
            (src / "About" / "About.xml").write_text("<ModMetaData />", encoding="utf-8")
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
            expected_dst = local_root / "_123456_"
            expected_source = normalize_path_for_storage(str(src))
            expected_success = normalize_path_for_storage(str(expected_dst))
            self.assertEqual(payload["source_paths"], [expected_source])
            self.assertEqual(payload["success_paths"], [expected_success])
            self.assertEqual(payload["size_check_paths"], [expected_source, expected_success])


if __name__ == "__main__":
    unittest.main()
