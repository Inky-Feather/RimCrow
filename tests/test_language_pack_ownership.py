import unittest

from backend.load_order.language_pack_ownership import (
    is_language_pack_mod,
    is_usable_language_pack_ownership,
    resolve_language_pack_ownership_for_mod,
)


class TestLanguagePackOwnership(unittest.TestCase):
    def test_usable_language_pack_ownership_accepts_medium_but_not_low(self):
        self.assertTrue(is_usable_language_pack_ownership({"summary_confidence": "medium"}))
        self.assertFalse(is_usable_language_pack_ownership({"summary_confidence": "low"}))

    def test_wide_detection_accepts_translation_with_patch_xml(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "zh.test.pack",
                "name": "Test Translation",
                "mod_type": "XML",
                "file_stats": {
                    "lang_xml": 3,
                    "patch_xml": 1,
                    "game_xml": 0,
                    "code_dll": 0,
                    "image": 0,
                    "audio": 0,
                },
                "rules": {
                    "dependencies": [{"target_id": "author.realmod"}],
                },
            },
            {
                "author.realmod": {
                    "package_id": "author.realmod",
                    "name": "Test Mod",
                },
            },
            wide_detection=True,
        )

        self.assertEqual(result["owners"], [{"package_id": "author.realmod"}])

    def test_user_mod_type_overrides_wide_detection(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "not.language.pack",
                "user_mod_type": "XML",
                "mod_type": "XML",
                "file_stats": {
                    "lang_xml": 3,
                    "patch_xml": 1,
                    "game_xml": 0,
                    "code_dll": 0,
                    "image": 0,
                    "audio": 0,
                },
                "rules": {
                    "dependencies": [{"target_id": "author.realmod"}],
                },
            },
            {
                "author.realmod": {
                    "package_id": "author.realmod",
                    "name": "Test Mod",
                },
            },
            wide_detection=True,
        )

        self.assertEqual(result["owners"], [])

    def test_explicit_wide_detection_ignores_stale_language_pack_flag(self):
        mod = {
            "package_id": "not.language.pack",
            "mod_type": "XML",
            "is_language_pack": True,
            "file_stats": {
                "lang_xml": 3,
                "patch_xml": 1,
                "game_xml": 0,
                "code_dll": 0,
                "image": 0,
                "audio": 0,
            },
        }

        self.assertFalse(is_language_pack_mod(mod, wide_detection=False))

    def test_uninstalled_dependency_candidate_is_low_confidence(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "zh.test.pack",
                "user_mod_type": "LanguagePack",
                "rules": {
                    "dependencies": [{"target_id": "missing.owner"}],
                },
            },
            {},
        )

        self.assertEqual(result["owners"], [{"package_id": "missing.owner"}])
        self.assertEqual(result["summary_confidence"], "low")

    def test_load_after_only_candidate_is_not_high_confidence(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "zh.test.pack",
                "user_mod_type": "LanguagePack",
                "rules": {
                    "load_after": [{"target_id": "author.realmod"}],
                },
            },
            {
                "author.realmod": {
                    "package_id": "author.realmod",
                    "name": "Test Mod",
                },
            },
        )

        self.assertEqual(result["owners"], [{"package_id": "author.realmod"}])
        self.assertEqual(result["summary_confidence"], "medium")

    def test_multiple_real_dependencies_remain_multiple_medium(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "zh.test.pack",
                "user_mod_type": "LanguagePack",
                "rules": {
                    "dependencies": [
                        {"target_id": "framework.mod"},
                        {"target_id": "author.realmod"},
                    ],
                },
            },
            {
                "framework.mod": {
                    "package_id": "framework.mod",
                    "name": "Framework",
                },
                "author.realmod": {
                    "package_id": "author.realmod",
                    "name": "Test Mod",
                },
            },
        )

        self.assertEqual(
            result["owners"],
            [{"package_id": "framework.mod"}, {"package_id": "author.realmod"}],
        )
        self.assertEqual(result["relation_type"], "multiple")
        self.assertEqual(result["summary_confidence"], "medium")

    def test_real_dependency_takes_priority_over_load_after_owner_candidates(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "zh.test.pack",
                "user_mod_type": "LanguagePack",
                "rules": {
                    "dependencies": [{"target_id": "author.realmod"}],
                    "load_after": [{"target_id": "patch.helper"}],
                },
            },
            {
                "author.realmod": {
                    "package_id": "author.realmod",
                    "name": "Test Mod",
                },
                "patch.helper": {
                    "package_id": "patch.helper",
                    "name": "Patch Helper",
                },
            },
        )

        self.assertEqual(result["owners"], [{"package_id": "author.realmod"}])
        self.assertEqual(result["relation_type"], "single")
        self.assertEqual(result["summary_confidence"], "high")

    def test_workshop_rule_in_effective_rules_is_used_as_language_pack_owner(self):
        result = resolve_language_pack_ownership_for_mod(
            {
                "package_id": "zh.test.pack",
                "user_mod_type": "LanguagePack",
                "rules": {
                    "load_after": [{
                        "target_id": "author.realmod",
                        "source": {"type": "workshop"},
                    }],
                },
            },
            {
                "author.realmod": {
                    "package_id": "author.realmod",
                    "name": "Test Mod",
                },
            },
        )

        self.assertEqual(result["owners"], [{"package_id": "author.realmod"}])

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
