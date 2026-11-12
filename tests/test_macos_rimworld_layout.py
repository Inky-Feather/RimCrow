import shutil
import tempfile
import unittest
from pathlib import Path

from backend.paths.game_locations import detect_rimworld_executable
from backend.paths.rimworld_layout import resolve_rimworld_layout


class TestMacOSRimWorldLayout(unittest.TestCase):
    """macOS 上 RimWorld 1.7 (Waylith) 与 1.6 及更早的包结构差异。"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _make_bundle(self, bundle: Path, executable_name: str, *, data_in_root: bool = False):
        (bundle / "Contents" / "MacOS").mkdir(parents=True)
        (bundle / "Contents" / "MacOS" / executable_name).write_text("", encoding="utf-8")
        if data_in_root:
            (bundle.parent / "Data" / "Core").mkdir(parents=True)
        else:
            (bundle / "Data" / "Core").mkdir(parents=True)

    def test_waylith_uses_rimworld_app_bundle(self):
        install_root = self.temp_dir / "RimWorld"
        bundle = install_root / "RimWorld.app"
        self._make_bundle(bundle, "RimWorld", data_in_root=True)

        layout = resolve_rimworld_layout(str(install_root), system_name="Darwin")

        self.assertEqual(layout.layout_kind, "mac_bundle")
        self.assertEqual(Path(layout.app_bundle_path).name, "RimWorld.app")
        self.assertTrue(Path(layout.app_bundle_path).exists())
        self.assertEqual(Path(layout.executable_path).name, "RimWorld")
        self.assertEqual(Path(layout.executable_path).parent.name, "MacOS")
        self.assertTrue(Path(layout.executable_path).exists())
        self.assertEqual(Path(layout.official_data_root).name, "Data")
        self.assertTrue(Path(layout.official_data_root).exists())
        self.assertEqual(Path(layout.local_mods_root).name, "Mods")

    def test_legacy_uses_rimworld_mac_app_bundle(self):
        install_root = self.temp_dir / "RimWorld"
        bundle = install_root / "RimWorldMac.app"
        self._make_bundle(bundle, "RimWorldMac")

        layout = resolve_rimworld_layout(str(install_root), system_name="Darwin")

        self.assertEqual(Path(layout.app_bundle_path).name, "RimWorldMac.app")
        self.assertEqual(Path(layout.executable_path).name, "RimWorldMac")
        self.assertTrue(Path(layout.executable_path).exists())
        self.assertTrue(Path(layout.official_data_root).exists())

    def test_app_bundle_path_itself_is_resolved(self):
        install_root = self.temp_dir / "RimWorld"
        bundle = install_root / "RimWorld.app"
        self._make_bundle(bundle, "RimWorld", data_in_root=True)

        layout = resolve_rimworld_layout(str(bundle), system_name="Darwin")

        self.assertEqual(layout.install_root, str(install_root))
        self.assertTrue(Path(layout.executable_path).exists())

    def test_detect_executable_returns_bundle_for_waylith(self):
        install_root = self.temp_dir / "RimWorld"
        bundle = install_root / "RimWorld.app"
        self._make_bundle(bundle, "RimWorld", data_in_root=True)

        detected = detect_rimworld_executable(str(install_root), system_name="Darwin")

        self.assertTrue(detected)
        self.assertEqual(Path(detected).name, "RimWorld.app")


if __name__ == "__main__":
    unittest.main()
