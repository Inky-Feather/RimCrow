import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.database.dao import ModDAO, ModMaintenanceDAO, _ProfilePathScope
from backend.database.models import MOD_ASSET_STATE_DELETED, MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_PRESENT, ModAsset, ModInterlock, UserModData, db
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.managers.mgr_profile import ProfileContext
from backend.scanner.mod_scanner import ModScanner
from backend.settings import settings
from backend.utils.tools import generate_path_hash, normalize_path_for_storage


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

    def test_find_missing_marks_deleted_state_and_keeps_last_path(self):
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
        self.assertEqual(asset.state, MOD_ASSET_STATE_DELETED)
        self.assertGreater(asset.file_modify_time, 0)

    def test_find_missing_marks_subscribed_workshop_record_as_missing(self):
        missing_path = str(Path(self.temp_dir.name) / "Workshop" / "123")
        ModAsset.create(
            path_hash="workshop-missing-hash",
            package_id="author.workshopmissing",
            name="Workshop Missing",
            path=missing_path,
            source="steam",
            store="workshop",
            workshop_id="123",
        )

        result = ModMaintenanceDAO.find_missing_mods(delete=False, subscribed_workshop_ids=["123"])
        asset = ModAsset.get_by_id("workshop-missing-hash")

        self.assertEqual(result["missing_mods"], ["workshop-missing-hash"])
        self.assertEqual(result["deleted_mods"], [])
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

    def test_delete_mod_record_keeps_physical_files(self):
        mod_dir = Path(self.temp_dir.name) / "Workshop" / "123"
        mod_dir.mkdir(parents=True)
        ModAsset.create(
            path_hash="record-only-hash",
            package_id="author.recordonly",
            name="Record Only",
            path=str(mod_dir),
            source="steam",
            store="workshop",
        )

        result = ModMaintenanceDAO.delete_mod_records(["record-only-hash"])

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["errors"], [])
        self.assertTrue(mod_dir.exists())
        self.assertIsNone(ModAsset.get_or_none(ModAsset.path_hash == "record-only-hash"))

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
        normalized_mod_dir = normalize_path_for_storage(mod_dir)
        path_hash = generate_path_hash(normalized_mod_dir)
        snapshot = {
            "mtime": int(stat.st_mtime * 1000),
            "size": 0,
            "package_id": "author.restored",
            "workshop_id": None,
            "disabled": False,
            "name": "Restored Mod",
            "version": "",
            "store": "local",
            "path": normalized_mod_dir,
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
        self.assertEqual(mod_data["path"], normalized_mod_dir)

    def _scanner_for_mod(self, temp_root: Path, package_id: str = "author.disabled"):
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
        scanner.xml_parser.parse.return_value = {"package_id": package_id, "url": "", "icon_path": ""}
        scanner.analyzer = Mock()
        scanner.analyzer.analyze.return_value = {"supported_languages": [], "file_stats": {}, "mod_type": "mod"}
        scanner._resolve_workshop_id = Mock(return_value=None)
        scanner._resolve_images = Mock(return_value=("", ""))
        return scanner

    def test_external_enabled_disabled_mod_is_counted_when_strict_mode_off(self):
        temp_root = Path(self.temp_dir.name)
        mod_dir = temp_root / "Mods" / "DisabledMod"
        about_file = mod_dir / "About" / "About.xml"
        about_file.parent.mkdir(parents=True)
        about_file.write_text("<ModMetaData />", encoding="utf-8")
        normalized_mod_dir = normalize_path_for_storage(mod_dir)
        path_hash = generate_path_hash(normalized_mod_dir)
        ModAsset.create(path_hash=path_hash, package_id="author.disabled", name="Disabled Mod", path=normalized_mod_dir, disabled=True)

        original_strict = getattr(settings.config, "strict_disabled_mode", False)
        self.addCleanup(setattr, settings.config, "strict_disabled_mode", original_strict)
        settings.config.strict_disabled_mode = False
        stats = {"external_enabled": 0}
        scan_details = {"external_enabled_mods": []}

        mod_data = self._scanner_for_mod(temp_root)._process_single_mod(
            str(mod_dir),
            False,
            existing_snapshots={path_hash: {"mtime": 0, "size": 0, "disabled": True, "package_id": "author.disabled", "name": "Disabled Mod", "path": normalized_mod_dir}},
            dlc_parser=None,
            forced_update=True,
            stats=stats,
            scan_details=scan_details,
        )

        self.assertFalse(mod_data["disabled"])
        self.assertEqual(stats["external_enabled"], 1)
        self.assertEqual(scan_details["external_enabled_mods"][0]["path_hash"], path_hash)

    def test_strict_mode_restores_external_enabled_disabled_mod(self):
        temp_root = Path(self.temp_dir.name)
        mod_dir = temp_root / "Mods" / "DisabledMod"
        about_file = mod_dir / "About" / "About.xml"
        disabled_file = mod_dir / "About" / "About.xml.disabled"
        about_file.parent.mkdir(parents=True)
        about_file.write_text("<ModMetaData />", encoding="utf-8")
        normalized_mod_dir = normalize_path_for_storage(mod_dir)
        path_hash = generate_path_hash(normalized_mod_dir)
        ModAsset.create(path_hash=path_hash, package_id="author.disabled", name="Disabled Mod", path=normalized_mod_dir, disabled=True)

        original_strict = getattr(settings.config, "strict_disabled_mode", False)
        self.addCleanup(setattr, settings.config, "strict_disabled_mode", original_strict)
        settings.config.strict_disabled_mode = True
        stats = {"strict_restored_disabled": 0, "strict_restore_failed": 0}
        scan_details = {"strict_restored_disabled_mods": [], "strict_restore_failed_mods": []}

        mod_data = self._scanner_for_mod(temp_root)._process_single_mod(
            str(mod_dir),
            False,
            existing_snapshots={path_hash: {"mtime": 0, "size": 0, "disabled": True, "package_id": "author.disabled", "name": "Disabled Mod", "path": normalized_mod_dir}},
            dlc_parser=None,
            forced_update=True,
            stats=stats,
            scan_details=scan_details,
        )

        self.assertTrue(mod_data["disabled"])
        self.assertFalse(about_file.exists())
        self.assertTrue(disabled_file.exists())
        self.assertEqual(stats["strict_restored_disabled"], 1)
        self.assertEqual(stats["strict_restore_failed"], 0)

    def test_strict_mode_restore_failure_keeps_database_disabled_state(self):
        temp_root = Path(self.temp_dir.name)
        mod_dir = temp_root / "Mods" / "DisabledMod"
        about_file = mod_dir / "About" / "About.xml"
        about_file.parent.mkdir(parents=True)
        about_file.write_text("<ModMetaData />", encoding="utf-8")
        normalized_mod_dir = normalize_path_for_storage(mod_dir)
        path_hash = generate_path_hash(normalized_mod_dir)
        ModAsset.create(path_hash=path_hash, package_id="author.disabled", name="Disabled Mod", path=normalized_mod_dir, disabled=True)

        original_strict = getattr(settings.config, "strict_disabled_mode", False)
        self.addCleanup(setattr, settings.config, "strict_disabled_mode", original_strict)
        settings.config.strict_disabled_mode = True
        stats = {"strict_restored_disabled": 0, "strict_restore_failed": 0}
        scan_details = {"strict_restored_disabled_mods": [], "strict_restore_failed_mods": []}

        with patch("backend.scanner.mod_scanner.ModMaintenanceDAO.set_mod_disabled_status", return_value=(False, "文件被占用")):
            mod_data = self._scanner_for_mod(temp_root)._process_single_mod(
                str(mod_dir),
                False,
                existing_snapshots={path_hash: {"mtime": 0, "size": 0, "disabled": True, "package_id": "author.disabled", "name": "Disabled Mod", "path": normalized_mod_dir}},
                dlc_parser=None,
                forced_update=True,
                stats=stats,
                scan_details=scan_details,
            )

        self.assertTrue(mod_data["disabled"])
        self.assertTrue(about_file.exists())
        self.assertEqual(stats["strict_restore_failed"], 1)
        self.assertEqual(scan_details["strict_restore_failed_mods"][0]["message"], "文件被占用")

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
                path=normalize_path_for_storage(path),
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

    def test_profile_disabled_mods_only_use_current_environment_paths(self):
        temp_root = Path(self.temp_dir.name)
        current_game = temp_root / "CurrentGame"
        other_game = temp_root / "OtherGame"
        workshop_root = temp_root / "Workshop"
        self_root = temp_root / "SelfMods"

        original_workshop = settings.config.workshop_mods_path
        original_self = settings.config.self_mods_path
        original_tool_enabled = settings.config.enable_tool_mods
        self.addCleanup(setattr, settings.config, "workshop_mods_path", original_workshop)
        self.addCleanup(setattr, settings.config, "self_mods_path", original_self)
        self.addCleanup(setattr, settings.config, "enable_tool_mods", original_tool_enabled)
        settings.config.workshop_mods_path = str(workshop_root)
        settings.config.self_mods_path = str(self_root)
        settings.config.enable_tool_mods = False

        rows = [
            ("current-local-disabled", current_game / "Mods" / "LocalDisabled", "local", True, MOD_ASSET_STATE_PRESENT),
            ("current-workshop-disabled", workshop_root / "123", "workshop", True, MOD_ASSET_STATE_PRESENT),
            ("current-self-disabled", self_root / "SelfDisabled", "self", True, MOD_ASSET_STATE_PRESENT),
            ("other-local-disabled", other_game / "Mods" / "OtherDisabled", "local", True, MOD_ASSET_STATE_PRESENT),
            ("current-local-enabled", current_game / "Mods" / "LocalEnabled", "local", False, MOD_ASSET_STATE_PRESENT),
            ("current-local-missing", current_game / "Mods" / "LocalMissing", "local", True, MOD_ASSET_STATE_MISSING),
        ]
        for path_hash, path, store, disabled, state in rows:
            ModAsset.create(
                path_hash=path_hash,
                package_id=f"author.{path_hash}",
                name=path_hash,
                path=normalize_path_for_storage(path),
                source=store,
                store=store,
                disabled=disabled,
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

        disabled_mods = ModDAO.get_profile_disabled_mods(context)
        disabled_hashes = {item["path_hash"] for item in disabled_mods}

        self.assertEqual(disabled_hashes, {
            "current-local-disabled",
            "current-workshop-disabled",
            "current-self-disabled",
        })

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
