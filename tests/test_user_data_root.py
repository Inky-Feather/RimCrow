import os
import unittest

from backend.profile.user_data_root import UserDataRoot


class TestUserDataRoot(unittest.TestCase):
    def test_from_raw_fixes_default_config_child_to_root(self):
        default_root = os.path.normpath("C:/Users/Test/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios")

        result = UserDataRoot.from_raw(
            default_root + "/Config",
            default_roots=[default_root],
        )

        self.assertEqual(result.root_path, default_root)
        self.assertTrue(result.was_corrected)
        self.assertEqual(result.config_dir, os.path.join(default_root, "Config"))
        self.assertEqual(result.mods_config_file, os.path.join(default_root, "Config", "ModsConfig.xml"))

    def test_from_raw_fixes_default_modsconfig_file_to_root(self):
        default_root = os.path.normpath("C:/Users/Test/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios")

        result = UserDataRoot.from_raw(
            default_root + "/Config/ModsConfig.xml",
            default_roots=[default_root],
        )

        self.assertEqual(result.root_path, default_root)
        self.assertTrue(result.was_corrected)

    def test_from_raw_rejects_non_default_child_path_guess(self):
        with self.assertRaises(ValueError):
            UserDataRoot.from_raw(
                "D:/Profiles/CustomProfile/Config",
                default_roots=["C:/Users/Test/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"],
            )
