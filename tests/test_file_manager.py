import unittest
from unittest.mock import patch

from backend.managers.mgr_files import FileManager


class TestFileManager(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
