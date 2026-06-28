import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.load_order.models import ParsedLoadOrderData
from backend.managers.mgr_load_order import LoadOrderManager


class TestLoadOrderManagerImportCheck(unittest.TestCase):
    def test_import_check_uses_visible_profile_mods_as_installed_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=False,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)
            parsed = ParsedLoadOrderData(
                format="modlist",
                list_name="Demo",
                package_ids=["author.package"],
                mod_names=["Demo Mod"],
                workshop_ids=["1234567890"],
            )
            visible_mods = [
                {
                    "package_id": "author.package",
                    "workshop_id": "1234567890",
                    "name": "Visible Mod",
                    "path": "X:/Visible/Mod",
                    "store": "workshop",
                }
            ]

            with patch("backend.managers.mgr_load_order.ModDAO.get_profile_mods", return_value=visible_mods) as get_profile_mods_mock, \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_package_ids", return_value={}), \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_workshop_ids", return_value={}), \
                 patch("backend.managers.mgr_load_order.build_import_check_report", return_value={"summary": {}, "items": []}) as build_report_mock:
                manager._build_import_check(parsed)

            get_profile_mods_mock.assert_called_once_with(context)
            self.assertEqual(build_report_mock.call_args.kwargs["installed_mods"], visible_mods)


if __name__ == "__main__":
    unittest.main()
