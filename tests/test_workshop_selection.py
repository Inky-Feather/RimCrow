import unittest

from backend.database.workshop_selection import select_best_workshop_detail_for_package
from backend.utils.tools import normalize_workshop_id


class TestWorkshopSelection(unittest.TestCase):
    def test_normalize_workshop_id_rejects_non_numeric_and_zero(self):
        self.assertEqual(normalize_workshop_id("0", digits_only=True, min_length=7, max_length=20), "")
        self.assertEqual(normalize_workshop_id("abc123", digits_only=True, min_length=7, max_length=20), "")
        self.assertEqual(normalize_workshop_id("1234567", digits_only=True, min_length=7, max_length=20), "1234567")

    def test_select_best_meta_prefers_matching_major_version_then_latest_update(self):
        metas = [
            {
                "workshop_id": "1111111111",
                "package_id": "author.package",
                "title": "Old Candidate",
                "author": "A",
                "game_versions": ["1.4"],
                "time_updated": 500,
            },
            {
                "workshop_id": "2222222222",
                "package_id": "author.package",
                "title": "Best Candidate",
                "author": "B",
                "game_versions": ["1.5"],
                "time_updated": 1000,
            },
            {
                "workshop_id": "3333333333",
                "package_id": "author.package",
                "title": "Older 1.5 Candidate",
                "author": "C",
                "game_versions": ["1.5.4069 rev95"],
                "time_updated": 600,
            },
        ]
        selected = select_best_workshop_detail_for_package(
            "author.package",
            meta_candidates=metas,
            replacement_candidates=[],
            current_game_version="1.5.4069 rev95",
        )
        self.assertEqual(selected["workshop_id"], "2222222222")

    def test_select_best_prefers_replacement_pool_when_available(self):
        metas = [
            {
                "workshop_id": "1111111111",
                "package_id": "legacy.package",
                "title": "Legacy Package",
                "author": "A",
                "game_versions": ["1.5"],
                "time_updated": 1000,
            }
        ]
        replacements = [
            {
                "old_package_id": "legacy.package",
                "new_workshop_id": "9999999999",
                "new_name": "Replacement Package",
                "new_versions": ["1.5"],
            }
        ]
        replacement_meta_map = {
            "9999999999": {
                "workshop_id": "9999999999",
                "package_id": "legacy.package",
                "title": "Replacement Package",
                "author": "B",
                "game_versions": ["1.5"],
                "time_updated": 800,
            }
        }
        selected = select_best_workshop_detail_for_package(
            "legacy.package",
            meta_candidates=metas,
            replacement_candidates=replacements,
            replacement_meta_map=replacement_meta_map,
            current_game_version="1.5.4069 rev95",
        )
        self.assertEqual(selected["workshop_id"], "9999999999")
        self.assertTrue(selected["is_replacement_derived"])


if __name__ == "__main__":
    unittest.main()
