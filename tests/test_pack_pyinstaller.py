import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

import pack_pyinstaller


class TestPackPyInstaller(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_prepare_pyinstaller_env_forces_stdlib_distutils(self):
        env = pack_pyinstaller._prepare_pyinstaller_env({"PATH": "/usr/bin"})

        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["SETUPTOOLS_USE_DISTUTILS"], "stdlib")

    def _prepare_pack_root(self) -> None:
        (self.temp_dir / "submodules" / "SteamworksPy" / "steamworks").mkdir(parents=True)
        (self.temp_dir / "submodules" / "SteamworksPy" / "steamworks" / "__init__.py").write_text("", encoding="utf-8")
        steamworks_dir = self.temp_dir / "tools" / "steamworks"
        steamworks_dir.mkdir(parents=True)
        for name in ("SteamworksPy.dylib", "libsteam_api.dylib"):
            (steamworks_dir / name).write_text("", encoding="utf-8")

    def test_pyinstaller_output_candidates_use_macos_app_layout(self):
        with patch("pack_pyinstaller.sys.platform", "darwin"):
            candidates = list(pack_pyinstaller._pyinstaller_output_candidates(Path("dist"), "RimCrow"))

        self.assertEqual(
            candidates,
            [
                Path("dist") / "RimCrow.app",
                Path("dist") / "RimCrow" / "RimCrow.app",
                Path("dist") / "RimCrow",
            ],
        )

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
        with zipfile.ZipFile(zip_path) as archive:
            self.assertIn("RimCrow/RimCrow.app/Contents/MacOS/RimCrow", archive.namelist())

    def test_create_release_zip_can_include_generated_docs(self):
        dist_dir = self.temp_dir / "dist"
        app_path = dist_dir / "RimCrow.exe"
        app_path.parent.mkdir(parents=True)
        app_path.write_text("bin", encoding="utf-8")
        docs_dir = self.temp_dir / "docs"
        (docs_dir / "zh-CN").mkdir(parents=True)
        (docs_dir / "RimCrow 使用说明.pdf").write_text("pdf", encoding="utf-8")
        (docs_dir / "zh-CN" / "01-快速上手.pdf").write_text("pdf", encoding="utf-8")

        fake_script = self.temp_dir / "pack_pyinstaller.py"
        fake_script.write_text("", encoding="utf-8")

        with patch.object(pack_pyinstaller, "__file__", str(fake_script)), \
             patch("pack_pyinstaller._iter_toolmods_files", return_value=[]), \
             patch("pack_pyinstaller._iter_tools_files", return_value=[]), \
             patch("pack_pyinstaller._iter_data_files", return_value=[]), \
             patch("pack_pyinstaller.sys.platform", "win32"):
            zip_path = pack_pyinstaller.create_release_zip("RimCrow", "1.2.3", docs_dir=docs_dir, include_docs=True)

        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            self.assertIn("RimCrow/docs/RimCrow 使用说明.pdf", names)
            self.assertIn("RimCrow/docs/zh-CN/01-快速上手.pdf", names)

    def test_build_release_docs_keeps_existing_pdfs_without_command(self):
        docs_dir = self.temp_dir / "docs"
        docs_dir.mkdir()
        existing_pdf = docs_dir / "manual.pdf"
        existing_pdf.write_text("pdf", encoding="utf-8")

        result = pack_pyinstaller.build_release_docs(
            project_root=self.temp_dir,
            output_dir=docs_dir,
        )

        self.assertIsNone(result)
        self.assertTrue(existing_pdf.exists())

    def test_build_release_docs_runs_configured_command(self):
        docs_dir = self.temp_dir / "docs"

        def fake_run(command, **kwargs):
            self.assertEqual(command, [sys.executable, "./local_tools/build_docs_pdf.py", "--output-dir", "docs"])
            docs_dir.mkdir(parents=True)
            (docs_dir / "manual.pdf").write_text("pdf", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok\n")

        with patch("pack_pyinstaller.subprocess.run", side_effect=fake_run):
            result = pack_pyinstaller.build_release_docs(
                project_root=self.temp_dir,
                output_dir=docs_dir,
                docs_config={
                    "command": [
                        "./local_tools/build_docs_pdf.py",
                        "--output-dir", "docs",
                    ],
                },
            )

        self.assertIsNone(result)
        self.assertTrue((docs_dir / "manual.pdf").exists())

    def test_build_release_docs_uses_configured_command_python(self):
        def fake_run(command, **kwargs):
            self.assertEqual(command, ["custom-python.exe", "./local_tools/build_docs_pdf.py"])
            return subprocess.CompletedProcess(command, 0, stdout="ok\n")

        with patch("pack_pyinstaller.subprocess.run", side_effect=fake_run):
            pack_pyinstaller.build_release_docs(
                project_root=self.temp_dir,
                output_dir=self.temp_dir / "docs",
                docs_config={
                    "command_python_executable": "custom-python.exe",
                    "command": ["./local_tools/build_docs_pdf.py"],
                },
            )

    def test_resolve_upx_dir_uses_configured_path(self):
        upx_dir = self.temp_dir / "upx"
        upx_dir.mkdir()

        self.assertEqual(pack_pyinstaller.resolve_upx_dir(str(upx_dir)), str(upx_dir))

    def test_load_pack_config_merges_local_overrides(self):
        config_path = self.temp_dir / "pack.local.json"
        config_path.write_text('{"steps": {"docs": false}, "app": {"upx_dir": "D:/upx"}}', encoding="utf-8")

        config = pack_pyinstaller.load_pack_config(config_path)

        self.assertFalse(config["steps"]["docs"])
        self.assertTrue(config["steps"]["app"])
        self.assertEqual(config["app"]["upx_dir"], "D:/upx")

    def test_windows_release_zip_name_unchanged(self):
        with patch("pack_pyinstaller.sys.platform", "win32"):
            name = pack_pyinstaller._release_zip_name("RimCrow", "1.2.3")

        self.assertEqual(name, "RimCrow-v1.2.3-windows.zip")

    def test_pack_application_uses_macos_onedir_and_skips_windows_options(self):
        self._prepare_pack_root()
        main_file = self.temp_dir / "main.py"
        main_file.write_text("print('ok')", encoding="utf-8")
        captured: dict[str, list[str]] = {}

        with patch.object(pack_pyinstaller, "__file__", str(self.temp_dir / "pack_pyinstaller.py")), \
             patch("pack_pyinstaller.sys.platform", "darwin"), \
             patch("pack_pyinstaller.create_pyinstaller_hook_dir", return_value=str(self.temp_dir / "hooks")), \
             patch("pack_pyinstaller._run_command_with_log", side_effect=lambda cmd, log_path, env=None: captured.setdefault("cmd", cmd) and 0):
            result = pack_pyinstaller.packApplication(
                main_file=str(main_file),
                icon_path="",
                name="RimCrow",
                splash_path="splash.png",
                version="1.2.3",
                company="Inky Feather",
                upx_dir="/tmp/upx",
            )

        self.assertTrue(result)
        cmd = captured["cmd"]
        self.assertIn("-D", cmd)
        self.assertNotIn("-F", cmd)
        self.assertNotIn("--version-file", cmd)
        self.assertNotIn("--splash", cmd)
        self.assertNotIn("--upx-dir", cmd)


if __name__ == "__main__":
    unittest.main()
