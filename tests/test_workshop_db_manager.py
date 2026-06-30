import gzip
import json
import tempfile
import unittest
from pathlib import Path

from backend.managers.mgr_workshop_db import WorkshopDBManager


class TestWorkshopDBManager(unittest.TestCase):
    def test_read_dataset_payload_detects_gzip_by_magic_bytes(self):
        payload = {
            "version": "2026-05-18",
            "rules": [
                {
                    "oldPackageId": "legacy.mod",
                    "newPackageId": "replacement.mod",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            misleading_path = Path(temp_dir) / "replacements.json"
            misleading_path.write_bytes(
                gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            )

            manager = object.__new__(WorkshopDBManager)
            loaded = manager._read_dataset_payload(misleading_path)

        self.assertEqual(loaded, payload)

    def test_require_dataset_field_rejects_missing_required_payload_field(self):
        manager = object.__new__(WorkshopDBManager)

        with self.assertRaises(ValueError) as ctx:
            manager._require_dataset_field({"version": "2026-05-18"}, "database", dict, "SteamDB")

        self.assertIn("database", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
