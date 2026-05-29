import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.database.dao import ModDAO, ModMaintenanceDAO, _ProfilePathScope
from backend.database.models import MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_PRESENT, ModAsset, ModInterlock, UserModData, db
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.managers.mgr_profile import ProfileContext
from backend.scanner.mod_scanner import ModScanner
from backend.utils.tools import generate_path_hash


class TestModAssetMissingState(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = str(Path(self.temp_dir.name) / "missing-state.db")
        db.init(db_path)
        db.connect(reuse_if_open=True)
        db.create_tables([ModAsset, ModInterlock, UserModData])

    def tearDown(self):
        if not db.is_closed():
            db.close()

    def test_find_missing_marks_state_and_keeps_last_path(self):
        missing_path = str(Path(self.temp_dir.name) / "Mods" / "LostMod")
        ModAsset.create(
            path_hash="lost-hash",
            package_id="author.lost",
            name="Lost Mod",
            path=missing_path,
            source="local",
            store="local",
        )

        result = ModMaintenanceDAO.find_missing_mods(delete=False)
        asset = ModAsset.get_by_id("lost-hash")

        self.assertEqual(result["deleted_mods"], ["lost-hash"])
        self.assertEqual(asset.path, missing_path)
        self.assertEqual(asset.state, MOD_ASSET_STATE_MISSING)
        self.assertGreater(asset.file_modify_time, 0)

    def test_delete_missing_record_counts_database_cleanup_as_success(self):
        missing_path = str(Path(self.temp_dir.name) / "Mods" / "LostMod")
        ModAsset.create(
            path_hash="lost-hash",
            package_id="author.lost",
            name="Lost Mod",
            path=missing_path,
            source="local",
            store="local",
            state=MOD_ASSET_STATE_MISSING,
        )

        result = ModMaintenanceDAO.delete_mods_physically(["lost-hash"])

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["errors"], [])
        self.assertIsNone(ModAsset.get_or_none(ModAsset.path_hash == "lost-hash"))

    def test_restored_missing_snapshot_is_parsed_instead_of_skipped(self):
        temp_root = Path(self.temp_dir.name)
        mod_dir = temp_root / "Mods" / "RestoredMod"
        about_file = mod_dir / "About" / "About.xml"
        about_file.parent.mkdir(parents=True)
        about_file.write_text("<ModMetaData />", encoding="utf-8")

        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(temp_root),
            user_data_path=str(temp_root / "userdata"),
            prefer_steam_launch=False,
            use_workshop_mods=False,
            use_self_mods=False,
        )
        scanner = ModScanner(context)
        scanner.xml_parser = Mock(return_value=None)
        scanner.xml_parser.parse.return_value = {"package_id": "author.restored", "url": "", "icon_path": ""}
        scanner.analyzer = Mock()
        scanner.analyzer.analyze.return_value = {
            "supported_languages": [],
            "file_stats": {},
            "mod_type": "mod",
        }
        scanner._resolve_workshop_id = Mock(return_value=None)
        scanner._resolve_images = Mock(return_value=("", ""))

        stat = about_file.stat()
        path_hash = generate_path_hash(str(mod_dir))
        snapshot = {
            "mtime": int(stat.st_mtime * 1000),
            "size": 0,
            "package_id": "author.restored",
            "workshop_id": None,
            "disabled": False,
            "name": "Restored Mod",
            "version": "",
            "store": "local",
            "path": str(mod_dir),
            "state": MOD_ASSET_STATE_MISSING,
            "supported_versions": [],
        }

        about_state = SimpleNamespace(resolved_path=str(about_file), is_disabled=False)
        with patch("backend.scanner.mod_scanner.ModAnalyzer.resolve_mod_about_state", return_value=about_state):
            mod_data = scanner._process_single_mod(
                str(mod_dir),
                False,
                existing_snapshots={path_hash: snapshot},
                dlc_parser=None,
                forced_update=False,
            )

        self.assertIsNotNone(mod_data)
        self.assertFalse(mod_data.get("_skipped"))
        self.assertEqual(mod_data["path_hash"], path_hash)
        self.assertEqual(mod_data["state"], MOD_ASSET_STATE_PRESENT)
        self.assertEqual(mod_data["path"], str(mod_dir))

    def test_workspace_classification_keeps_missing_assets_in_original_domain(self):
        scope = _ProfilePathScope(
            local_root=_ProfilePathScope._normalize_root(str(Path(self.temp_dir.name) / "Mods")),
            workshop_root=_ProfilePathScope._normalize_root(str(Path(self.temp_dir.name) / "Workshop")),
        )

        workshop_domain = scope.classify_asset({
            "path": str(Path(self.temp_dir.name) / "Workshop" / "123"),
            "store": "workshop",
            "state": MOD_ASSET_STATE_MISSING,
        })
        local_domain = scope.classify_asset({
            "path": str(Path(self.temp_dir.name) / "Mods" / "LostMod"),
            "store": "local",
            "state": MOD_ASSET_STATE_MISSING,
        })

        self.assertEqual(workshop_domain, "workshop")
        self.assertEqual(local_domain, "local")

    def test_workspace_domain_assets_only_show_current_profile_local_paths(self):
        temp_root = Path(self.temp_dir.name)
        current_game = temp_root / "CurrentGame"
        other_game = temp_root / "OtherGame"
        rows = [
            ("current-present", current_game / "Mods" / "CurrentPresent", MOD_ASSET_STATE_PRESENT),
            ("current-missing", current_game / "Mods" / "CurrentMissing", MOD_ASSET_STATE_MISSING),
            ("other-present", other_game / "Mods" / "OtherPresent", MOD_ASSET_STATE_PRESENT),
            ("other-missing", other_game / "Mods" / "OtherMissing", MOD_ASSET_STATE_MISSING),
        ]
        for path_hash, path, state in rows:
            ModAsset.create(
                path_hash=path_hash,
                package_id=f"author.{path_hash}",
                name=path_hash,
                path=str(path),
                source="local",
                store="local",
                state=state,
            )

        context = ProfileContext(
            profile_id="current",
            game_version="1.5.4100",
            game_install_path=str(current_game),
            user_data_path=str(temp_root / "userdata"),
            prefer_steam_launch=False,
            use_workshop_mods=False,
            use_self_mods=False,
        )

        matrix = ModDAO.get_triple_domain_assets(context)
        local_hashes = {item["path_hash"] for item in matrix["local"]}

        self.assertEqual(local_hashes, {"current-present", "current-missing"})

    def test_probe_item_availability_marks_empty_details_unavailable(self):
        workshop_id = "2941001234"
        payload = {
            "response": {
                "publishedfiledetails": [
                    {"publishedfileid": workshop_id, "result": 9, "title": "", "preview_url": "", "time_updated": 0}
                ]
            }
        }
        with patch.object(SteamWebAPI, "_request_json", return_value=payload):
            result = SteamWebAPI.probe_item_availability([workshop_id])

        self.assertEqual(result[workshop_id]["status"], "unavailable")
        self.assertIsNone(result[workshop_id]["online_info"])
