import shutil
import tempfile
import unittest
from pathlib import Path

from backend.load_order import (
    FORMAT_MODLIST,
    FORMAT_MODSCONFIG,
    FORMAT_PLAIN_TEXT,
    FORMAT_RML,
    FORMAT_RIMPY_XML,
    FORMAT_RIMSORT_JSON,
    FORMAT_RMM_JSON,
    FORMAT_SAVEGAME,
    FORMAT_WORKSHOP_IDS,
    detect_load_order_format,
    parse_load_order_file,
)


class TestLoadOrderParsers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.temp_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_detect_modsconfig_xml(self):
        path = self._write(
            "ModsConfig.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<ModsConfigData>
  <activeMods>
    <li>ludeon.rimworld</li>
    <li>brrainz.harmony</li>
  </activeMods>
</ModsConfigData>""",
        )
        self.assertEqual(detect_load_order_format(path), FORMAT_MODSCONFIG)

    def test_parse_modlist_xml(self):
        path = self._write(
            "MyList.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<ModList>
  <Name>Example List</Name>
  <modIds>
    <li>brrainz.harmony</li>
    <li>ludeon.rimworld</li>
  </modIds>
  <modNames>
    <li>Harmony</li>
    <li>Core</li>
  </modNames>
  <modSteamWorkshopIds>
    <li>2009463077</li>
    <li>0</li>
  </modSteamWorkshopIds>
</ModList>""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_MODLIST)
        self.assertEqual(parsed.list_name, "Example List")
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.mod_names, ["Harmony", "Core"])
        self.assertEqual(parsed.workshop_ids, ["2009463077", "0"])

    def test_parse_savegame_xml(self):
        path = self._write(
            "save.rws",
            """<savegame>
  <meta>
    <modIds>
      <li>brrainz.harmony</li>
      <li>ludeon.rimworld</li>
    </modIds>
    <modNames>
      <li>Harmony</li>
      <li>Core</li>
    </modNames>
    <modSteamIds>
      <li>2009463077</li>
      <li>0</li>
    </modSteamIds>
  </meta>
</savegame>""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_SAVEGAME)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])

    def test_parse_rml_file(self):
        path = self._write(
            "sample.rml",
            """<?xml version="1.0" encoding="utf-8"?>
<savedModList>
  <meta>
    <gameVersion>1.5.4069 rev95</gameVersion>
    <modIds>
      <li>brrainz.harmony</li>
      <li>ludeon.rimworld</li>
    </modIds>
    <modSteamIds>
      <li>2009463077</li>
      <li>0</li>
    </modSteamIds>
    <modNames>
      <li>Harmony</li>
      <li>Core</li>
    </modNames>
  </meta>
  <modList>
    <ids>
      <li>brrainz.harmony</li>
      <li>ludeon.rimworld</li>
    </ids>
    <names>
      <li>Harmony CN</li>
      <li>Core CN</li>
    </names>
  </modList>
</savedModList>""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_RML)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.mod_names, ["Harmony CN", "Core CN"])
        self.assertEqual(parsed.workshop_ids, ["2009463077", "0"])

    def test_parse_rimsort_json(self):
        path = self._write(
            "rimsort.json",
            """{
  "name": "RimSort Export",
  "mods": [
    {"packageId": "brrainz.harmony", "name": "Harmony", "workshopId": "2009463077"},
    {"packageId": "ludeon.rimworld", "name": "Core"}
  ]
}""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_RIMSORT_JSON)
        self.assertEqual(parsed.list_name, "RimSort Export")
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.mod_names, ["Harmony", "Core"])

    def test_parse_rimpy_xml(self):
        path = self._write(
            "rimpy.xml",
            """<RimPyModList>
  <mod packageId="brrainz.harmony" name="Harmony" workshopId="2009463077" />
  <mod packageId="ludeon.rimworld" name="Core" />
</RimPyModList>""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_RIMPY_XML)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.mod_names, ["Harmony", "Core"])

    def test_parse_plain_text_mixed(self):
        path = self._write(
            "mods.txt",
            """# comment
brrainz.harmony
https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077
ludeon.rimworld
""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_PLAIN_TEXT)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertIn("2009463077", parsed.workshop_ids)

    def test_parse_rimsort_clipboard_report_text(self):
        path = self._write(
            "rimsort_report.txt",
            """Created with RimSort v1.0.69
RimWorld game version this list was created for: 1.6.4633 rev1260
Total # of mods: 4

Harmony [brrainz.harmony][https://github.com/pardeike/HarmonyRimWorld]
RimModManager Companion [rmm.companion][No url specified]
Adaptive Storage Framework [adaptive.storage.framework][https://steamcommunity.com/sharedfiles/filedetails/?id=3033901359]
RimWorld [ludeon.rimworld][https://store.steampowered.com/app/294100/RimWorld]
""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_PLAIN_TEXT)
        self.assertEqual(
            parsed.package_ids,
            [
                "brrainz.harmony",
                "rmm.companion",
                "adaptive.storage.framework",
                "ludeon.rimworld",
            ],
        )
        self.assertEqual(
            parsed.mod_names,
            [
                "Harmony",
                "RimModManager Companion",
                "Adaptive Storage Framework",
                "RimWorld",
            ],
        )
        self.assertEqual(parsed.workshop_ids[:4], ["", "", "3033901359", ""])
        self.assertEqual(parsed.warnings, [])
        self.assertEqual(parsed.errors, [])

    def test_parse_workshop_ids_text(self):
        path = self._write(
            "workshop.txt",
            """2009463077
2873415404
https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890
""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_WORKSHOP_IDS)
        self.assertEqual(parsed.package_ids, [])
        self.assertEqual(parsed.workshop_ids, ["2009463077", "2873415404", "1234567890"])

    def test_parse_rmm_json(self):
        path = self._write(
            "rmm.json",
            """{
  "package_ids": ["brrainz.harmony", "ludeon.rimworld"],
  "mod_names": {
    "brrainz.harmony": "Harmony",
    "ludeon.rimworld": "Core"
  },
  "workshop_ids": ["2009463077"]
}""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_RMM_JSON)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.mod_names, ["Harmony", "Core"])

    def test_detect_and_parse_rimsort_json_content_saved_as_xml(self):
        path = self._write(
            "RimSortExport.xml",
            """{
  "version": "1.6.4633 rev1260",
  "activeMods": [
    "brrainz.harmony",
    "ludeon.rimworld"
  ],
  "knownExpansions": []
}""",
        )
        self.assertEqual(detect_load_order_format(path), FORMAT_RIMSORT_JSON)
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_RIMSORT_JSON)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.errors, [])

    def test_duplicate_package_ids_keep_first_occurrence(self):
        path = self._write(
            "duplicate_modlist.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<ModList>
  <Name>Duplicate List</Name>
  <modIds>
    <li>brrainz.harmony</li>
    <li>brrainz.harmony</li>
    <li>ludeon.rimworld</li>
  </modIds>
  <modNames>
    <li>Harmony A</li>
    <li>Harmony B</li>
    <li>Core</li>
  </modNames>
  <modSteamWorkshopIds>
    <li>2009463077</li>
    <li>9999999999</li>
    <li>0</li>
  </modSteamWorkshopIds>
</ModList>""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.package_ids, ["brrainz.harmony", "ludeon.rimworld"])
        self.assertEqual(parsed.mod_names, ["Harmony A", "Core"])
        self.assertEqual(parsed.workshop_ids[:2], ["2009463077", "0"])

    def test_duplicate_workshop_ids_keep_first_occurrence(self):
        path = self._write(
            "duplicate_workshop.txt",
            """2009463077
2009463077
2873415404
2873415404
""",
        )
        parsed = parse_load_order_file(path)
        self.assertEqual(parsed.format, FORMAT_WORKSHOP_IDS)
        self.assertEqual(parsed.workshop_ids, ["2009463077", "2873415404"])


if __name__ == "__main__":
    unittest.main()
