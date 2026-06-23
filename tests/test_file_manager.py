import os
import struct
import tempfile
import unittest
import zlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.managers.mgr_files import FileManager, LocalAssetHandler


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


if __name__ == "__main__":
    unittest.main()
