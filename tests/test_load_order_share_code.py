import unittest

from backend.load_order import FORMAT_SHARE_CODE, build_share_code, describe_share_code, parse_share_code


class TestLoadOrderShareCode(unittest.TestCase):
    def test_share_code_round_trip_preserves_order_and_metadata(self):
        share_code = build_share_code(
            package_ids=["brrainz.harmony", "ludeon.rimworld", "unlimitedhugs.hugslib"],
            mod_names=["Harmony", "Core", "HugsLib"],
            workshop_ids=["2009463077", "0", "818773962"],
            list_name="My Shared Order",
            game_version="1.5.4104",
        )
        self.assertTrue(share_code.startswith("RC-"))

        parsed = parse_share_code(share_code)
        self.assertEqual(parsed.format, FORMAT_SHARE_CODE)
        self.assertEqual(parsed.list_name, "My Shared Order")
        self.assertEqual(
            parsed.package_ids,
            ["brrainz.harmony", "ludeon.rimworld", "unlimitedhugs.hugslib"],
        )
        self.assertEqual(parsed.mod_names, ["Harmony", "Core", "HugsLib"])
        self.assertEqual(parsed.workshop_ids, ["2009463077", "", "818773962"])

    def test_share_code_parser_tolerates_whitespace(self):
        share_code = build_share_code(
            package_ids=["brrainz.harmony"],
            mod_names=["Harmony"],
            workshop_ids=["2009463077"],
        )
        padded_code = f"  {share_code[:12]}\n{share_code[12:]}  "
        parsed = parse_share_code(padded_code)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony"])
        self.assertEqual(parsed.workshop_ids, ["2009463077"])

    def test_share_code_checksum_rejects_tampering(self):
        share_code = build_share_code(package_ids=["brrainz.harmony"])
        tampered = share_code[:-1] + ("A" if share_code[-1] != "A" else "B")
        with self.assertRaisesRegex(ValueError, "校验失败"):
            parse_share_code(tampered)

    def test_describe_share_code_returns_short_ref(self):
        share_code = build_share_code(package_ids=["brrainz.harmony"])
        description = describe_share_code(share_code)
        self.assertTrue(description.startswith("share://RC/"))

    def test_legacy_rmm1_share_code_still_imports(self):
        share_code = build_share_code(package_ids=["brrainz.harmony"])
        legacy_code = "RMM1-" + share_code[len("RC-"):]

        parsed = parse_share_code(legacy_code)

        self.assertEqual(parsed.package_ids, ["brrainz.harmony"])


if __name__ == "__main__":
    unittest.main()
