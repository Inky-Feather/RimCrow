import unittest

from backend.load_order.language_pack_ownership import resolve_language_pack_ownership_for_mod


class TestLanguagePackOwnership(unittest.TestCase):
    def test_user_override_can_point_to_hard_noise_owner(self):
        mods = [
            {
                "package_id": "zh.test.pack",
                "name": "Test Mod Chinese Pack",
                "user_mod_type": "LanguagePack",
                "rules": {
                    "dependencies": [
                        {"package_id": "brrainz.harmony"},
                    ],
                    "load_after": [
                        {"package_id": "author.realmod"},
                    ],
                },
            },
            {
                "package_id": "author.realmod",
                "name": "Test Mod",
            },
            {
                "package_id": "brrainz.harmony",
                "name": "Harmony",
            },
        ]
        asset_index = {
            str(mod["package_id"]).lower(): {
                "package_id": str(mod["package_id"]).lower(),
                "name": mod.get("name") or "",
                "mod_type": mod.get("mod_type") or "",
                "user_mod_type": mod.get("user_mod_type") or "",
            }
            for mod in mods
        }

        result = resolve_language_pack_ownership_for_mod(
            mods[0],
            asset_index,
            user_mod_rules={
                "zh.test.pack": {
                    "languagePackOwners": {
                        "owners": ["brrainz.harmony"],
                        "replace": False,
                    }
                }
            },
        )

        self.assertEqual(result["owners"], [{"package_id": "author.realmod"}, {"package_id": "brrainz.harmony"}])


if __name__ == "__main__":
    unittest.main()
