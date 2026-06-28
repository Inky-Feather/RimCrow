import shutil
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

class _PeeweeModel:
    pass


peewee_stub = types.ModuleType("peewee")
peewee_stub.Model = _PeeweeModel
peewee_stub.JOIN = object()
sys.modules.setdefault("peewee", peewee_stub)

playhouse_stub = types.ModuleType("playhouse")
playhouse_shortcuts_stub = types.ModuleType("playhouse.shortcuts")
playhouse_shortcuts_stub.model_to_dict = lambda value, *args, **kwargs: value
sys.modules.setdefault("playhouse", playhouse_stub)
sys.modules.setdefault("playhouse.shortcuts", playhouse_shortcuts_stub)

webview_stub = types.ModuleType("webview")
webview_stub.WebViewException = Exception
webview_stub.Window = object
sys.modules.setdefault("webview", webview_stub)


def _stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules.setdefault(name, module)


class _Dummy:
    pass


class _DummyDao:
    @staticmethod
    def get_all_mods_with_user_data(*args, **kwargs):
        return []

    @staticmethod
    def get_profile_mods(*args, **kwargs):
        return []


_stub_module("backend.managers.mgr_steamcmd_core", SteamCMDController=_Dummy)
_stub_module("backend.managers.mgr_network", network_mgr=_Dummy())
_stub_module(
    "backend.database.models",
    ModAsset=_Dummy,
    ModInterlock=_Dummy,
    UserModData=_Dummy,
    GithubModRecord=_Dummy,
    GithubTimeline=_Dummy,
    db=_Dummy(),
)
_stub_module(
    "backend.database.dao",
    CollectionDAO=_Dummy,
    GroupDAO=_Dummy,
    ModDAO=_DummyDao,
    ModInterlockDAO=_Dummy,
    ModMaintenanceDAO=_Dummy,
)
_stub_module("backend.database.dao_ext", ExtDAO=_Dummy)
_stub_module("backend.database.runtime", close_db=lambda: None, clear_db=lambda: None, init_db=lambda *args, **kwargs: True)
_stub_module(
    "backend.database.repair",
    _cleanup_database_sidecars=lambda *args, **kwargs: None,
    _cleanup_repair_artifacts=lambda *args, **kwargs: None,
    _remove_file_with_retry=lambda *args, **kwargs: None,
    prepare_database_for_startup=lambda *args, **kwargs: {"actions_taken": [], "messages": [], "created_clean_database": False},
    prepare_manual_database_repair=lambda *args, **kwargs: {},
)
_stub_module("backend.scanner.parser_dlc", DLCParser=_Dummy)
_stub_module("backend.scanner.mod_scanner", ModScanner=_Dummy)
_stub_module("backend.managers.mgr_game", GameManager=_Dummy)
_stub_module("backend.managers.mgr_game_install", GameInstallInspector=_Dummy)
_stub_module("backend.managers.mgr_load_order", LoadOrderManager=_Dummy)
_stub_module("backend.managers.mgr_files", FileManager=_Dummy, file_mgr=_Dummy(), PathChecker=_Dummy)
_stub_module("backend.managers.mgr_game_logs", GameLogManager=_Dummy, LogCondenser=_Dummy)
_stub_module("backend.managers.mgr_sorter", OrderSorter=_Dummy)
_stub_module("backend.managers.mgr_download", DownloadManager=_Dummy, TaskStatus=_Dummy)
_stub_module("backend.managers.mgr_steam", RIMWORLD_APP_ID=294100, SteamManager=_Dummy)
_stub_module("backend.managers.mgr_sub_browser", SubBrowserManager=_Dummy)
_stub_module("backend.ai.ai_service", AIManager=_Dummy)
_stub_module("backend.managers.mgr_workshop_db", WorkshopDBManager=_Dummy)
_stub_module("backend.managers.mgr_update", UpdateManager=_Dummy, UpdateInfo=_Dummy)
_stub_module("backend.managers.mgr_game_monitor", GameMonitor=_Dummy)
_stub_module("backend.managers.mgr_profile", ProfileContext=_Dummy, ProfileManager=_Dummy)
_stub_module("backend.managers.mgr_mod_config", ModConfigManager=_Dummy)
_stub_module("backend.managers.mgr_steam_api", SteamWebAPI=_Dummy)
_stub_module("backend.managers.mgr_github", GithubManager=_Dummy)
_stub_module("backend.managers.mgr_maintenance", MaintenanceManager=_Dummy)
_stub_module("backend.managers.mgr_data_bundle", DataBundleManager=_Dummy)
_stub_module("backend.managers.mgr_mod_package", ModPackageManager=_Dummy)
_stub_module("backend.load_order.language_pack_ownership", resolve_language_pack_ownership_for_mods=lambda *args, **kwargs: {})
_stub_module("backend.browser_runtime", build_sub_browser_target_url=lambda *args, **kwargs: "")
_stub_module("backend.utils.restart", launch_new_application=lambda *args, **kwargs: None)
_stub_module(
    "backend.migrations.app_upgrade",
    normalize_duplicate_group_names_on_load=lambda *args, **kwargs: None,
    run_app_upgrade_migrations=lambda *args, **kwargs: None,
)
_stub_module("backend.text_search.manager", FileSearchManager=_Dummy)

from backend.api import API
from backend.managers.mgr_texture_opt import TextureTargetResolver
from backend.settings import settings


class TestTextureOptApiHelpers(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        self.local_root = self.temp_root / "LocalMods"
        self.self_root = self.temp_root / "SelfMods"
        self.workshop_root = self.temp_root / "WorkshopMods"
        for root in [self.local_root, self.self_root, self.workshop_root]:
            root.mkdir(parents=True, exist_ok=True)
        (self.local_root / "LocalA").mkdir()
        (self.self_root / "SelfA").mkdir()
        (self.workshop_root / "WorkshopA").mkdir()
        (self.workshop_root / "nested.txt").write_text("ignore", encoding="utf-8")

        self.active_context = SimpleNamespace(
            local_mods_path=str(self.local_root),
            use_self_mods=True,
        )
        self.api = API.__new__(API)
        self.api.active_context = self.active_context

    def test_texture_target_resolver_scans_direct_children_and_keeps_instance_metadata(self):
        local_path = os.path.normcase(os.path.abspath(str(self.local_root / "LocalA")))
        workshop_path = os.path.normcase(os.path.abspath(str(self.workshop_root / "WorkshopA")))

        with patch.object(settings.config, "self_mods_path", str(self.self_root)), \
             patch.object(settings.config, "workshop_mods_path", str(self.workshop_root)), \
             patch("backend.managers.mgr_texture_opt.resolve_profile_runtime_capabilities", return_value={"workshop_detection_enabled": True}), \
             patch("backend.database.dao.ModDAO.get_all_mods_with_user_data", return_value=[
                 {
                     "path": local_path,
                     "package_id": "Local.Mod",
                     "display_name": "Local A",
                     "path_hash": "local-hash",
                     "store": "local",
                 },
                 {
                     "path": workshop_path,
                     "package_id": "Workshop.Mod",
                     "display_name": "Workshop A",
                     "path_hash": "workshop-hash",
                     "store": "workshop",
                 },
             ]):
            targets = TextureTargetResolver(self.active_context).collect_all_targets()

        by_path = {os.path.normcase(os.path.abspath(item["mod_path"])): item for item in targets}
        self.assertEqual(set(by_path), {
            local_path,
            os.path.normcase(os.path.abspath(str(self.self_root / "SelfA"))),
            workshop_path,
        })
        self.assertEqual(by_path[local_path]["package_id"], "local.mod")
        self.assertEqual(by_path[local_path]["path_hash"], "local-hash")
        self.assertEqual(by_path[local_path]["mod_instance_key"], "local-hash")
        self.assertEqual(by_path[workshop_path]["package_id"], "workshop.mod")
        self.assertEqual(by_path[workshop_path]["store"], "workshop")

    def test_texture_analyze_mods_all_scope_allows_empty_package_list(self):
        api = API.__new__(API)
        api.active_context = None
        targets = [{
            "mod_path": r"C:\Mods\A",
            "mod_name": "A",
            "package_id": "example.mod",
            "path_hash": "hash-a",
            "mod_instance_key": "hash-a",
            "store": "local",
        }]
        api.texture_mgr = SimpleNamespace(
            resolve_targets=Mock(return_value=targets),
            start_analysis_task=Mock(return_value={"task_id": "task-a"}),
        )

        response = api.texture_analyze_mods([], {"target_scope": "all"})

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["message"], "贴图分析任务已在后台启动")
        api.texture_mgr.resolve_targets.assert_called_once_with([], "all", getattr(api, "active_context", None))
        api.texture_mgr.start_analysis_task.assert_called_once_with(targets, {"target_scope": "all"})


if __name__ == "__main__":
    unittest.main()
