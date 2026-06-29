import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from backend.migrations.app_relocation import apply_config_relocation


@dataclass
class TextureConfigStub:
    texture_tools_path: str = ""


@dataclass
class ConfigStub:
    home_path: str
    self_mods_path: str
    steamcmd_path: str
    ripgrep_path: str
    community_workshop_db_path: str
    user_rules_path: str
    workshop_mods_path: str
    steam_path: str
    texture_opt: TextureConfigStub


class TestAppRelocation(unittest.TestCase):
    def test_config_relocation_rewrites_only_internal_paths(self):
        old_home = Path(tempfile.mkdtemp())
        new_home = Path(tempfile.mkdtemp())
        external_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(old_home, ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(new_home, ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(external_root, ignore_errors=True))

        config = ConfigStub(
            home_path=str(old_home),
            self_mods_path=str(old_home / "mods"),
            steamcmd_path=str(old_home / "tools" / "steamcmd"),
            ripgrep_path=str(old_home / "tools" / "ripgrep"),
            community_workshop_db_path=str(old_home / "data" / "steamDB.json"),
            user_rules_path=str(old_home / "data" / "rules" / "user_rules.json"),
            workshop_mods_path=str(external_root / "workshop"),
            steam_path=str(external_root / "Steam"),
            texture_opt=TextureConfigStub(str(old_home / "tools" / "texture_tools")),
        )

        result = apply_config_relocation(config, str(old_home), str(new_home))

        self.assertTrue(result.moved)
        self.assertEqual(config.home_path, str(new_home))
        self.assertEqual(config.self_mods_path, str(new_home / "mods"))
        self.assertEqual(config.steamcmd_path, str(new_home / "tools" / "steamcmd"))
        self.assertEqual(config.ripgrep_path, str(new_home / "tools" / "ripgrep"))
        self.assertEqual(config.community_workshop_db_path, str(new_home / "data" / "steamDB.json"))
        self.assertEqual(config.user_rules_path, str(new_home / "data" / "rules" / "user_rules.json"))
        self.assertEqual(config.texture_opt.texture_tools_path, str(new_home / "tools" / "texture_tools"))
        self.assertEqual(config.workshop_mods_path, str(external_root / "workshop"))
        self.assertEqual(config.steam_path, str(external_root / "Steam"))

    def test_config_relocation_noops_when_home_is_same(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))
        config = ConfigStub(
            home_path=str(home),
            self_mods_path=str(home / "mods"),
            steamcmd_path=str(home / "tools" / "steamcmd"),
            ripgrep_path=str(home / "tools" / "ripgrep"),
            community_workshop_db_path=str(home / "data" / "steamDB.json"),
            user_rules_path=str(home / "data" / "rules" / "user_rules.json"),
            workshop_mods_path="",
            steam_path="",
            texture_opt=TextureConfigStub(str(home / "tools" / "texture_tools")),
        )

        result = apply_config_relocation(config, str(home), str(home))

        self.assertFalse(result.moved)
        self.assertEqual(result.config_updates, {})

    def test_config_relocation_resolves_relative_paths_from_old_home(self):
        old_home = Path(tempfile.mkdtemp())
        new_home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(old_home, ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(new_home, ignore_errors=True))
        config = ConfigStub(
            home_path=str(old_home),
            self_mods_path="mods",
            steamcmd_path="tools/steamcmd",
            ripgrep_path="tools/ripgrep",
            community_workshop_db_path="data/steamDB.json",
            user_rules_path="data/rules/user_rules.json",
            workshop_mods_path="",
            steam_path="",
            texture_opt=TextureConfigStub("tools/texture_tools"),
        )

        result = apply_config_relocation(config, str(old_home), str(new_home))

        self.assertTrue(result.moved)
        self.assertEqual(config.self_mods_path, str(new_home / "mods"))
        self.assertEqual(config.steamcmd_path, str(new_home / "tools" / "steamcmd"))
        self.assertEqual(config.texture_opt.texture_tools_path, str(new_home / "tools" / "texture_tools"))


if __name__ == "__main__":
    unittest.main()
