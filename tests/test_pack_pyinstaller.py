import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pack_pyinstaller


class TestPackPyInstaller(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_resolve_output_prefers_macos_app_bundle(self):
        app_bundle = self.temp_dir / "RimCrow.app"
        (app_bundle / "Contents" / "MacOS").mkdir(parents=True)

        with patch("pack_pyinstaller.sys.platform", "darwin"):
            output_path = pack_pyinstaller._resolve_pyinstaller_output(self.temp_dir, "RimCrow")

        self.assertEqual(output_path, app_bundle)

    def test_iter_release_output_files_expands_app_bundle(self):
        app_bundle = self.temp_dir / "RimCrow.app"
        binary_path = app_bundle / "Contents" / "MacOS" / "RimCrow"
        binary_path.parent.mkdir(parents=True)
        binary_path.write_text("bin", encoding="utf-8")

        items = list(pack_pyinstaller._iter_release_output_files(app_bundle))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], binary_path)
        self.assertEqual(items[0][1], Path("RimCrow.app") / "Contents" / "MacOS" / "RimCrow")

    def test_create_release_zip_uses_platform_output_not_exe_only(self):
        dist_dir = self.temp_dir / "dist"
        app_bundle = dist_dir / "RimCrow.app"
        binary_path = app_bundle / "Contents" / "MacOS" / "RimCrow"
        binary_path.parent.mkdir(parents=True)
        binary_path.write_text("bin", encoding="utf-8")

        fake_script = self.temp_dir / "pack_pyinstaller.py"
        fake_script.write_text("", encoding="utf-8")

        with patch.object(pack_pyinstaller, "__file__", str(fake_script)), \
             patch("pack_pyinstaller._iter_toolmods_files", return_value=[]), \
             patch("pack_pyinstaller._iter_tools_files", return_value=[]), \
             patch("pack_pyinstaller._iter_data_files", return_value=[]), \
             patch("pack_pyinstaller.sys.platform", "darwin"):
            zip_path = pack_pyinstaller.create_release_zip("RimCrow", "1.2.3")

        self.assertTrue(zip_path.exists())
        self.assertEqual(zip_path.name, "RimCrow-v1.2.3-macos.zip")

    def test_windows_release_zip_name_unchanged(self):
        with patch("pack_pyinstaller.sys.platform", "win32"):
            name = pack_pyinstaller._release_zip_name("RimCrow", "1.2.3")

        self.assertEqual(name, "RimCrow-v1.2.3-windows.zip")
