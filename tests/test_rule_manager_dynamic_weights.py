import importlib
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

_STUBBED_MODULE_NAMES = [
    "backend.managers.mgr_rules",
    "backend.database.dao",
    "backend.managers.mgr_profile",
    "peewee",
]
_ORIGINAL_MODULES = {name: sys.modules.get(name) for name in _STUBBED_MODULE_NAMES}


fake_dao_module = types.ModuleType("backend.database.dao")
fake_dao_module.ModDAO = Mock()
fake_dao_module.GroupDAO = Mock()
fake_dao_module.normalize_interlock_payload = lambda payload: payload
fake_dao_module.normalize_user_mod_data_payload = lambda payload: payload
sys.modules["backend.database.dao"] = fake_dao_module

fake_profile_module = types.ModuleType("backend.managers.mgr_profile")
fake_profile_module.ProfileContext = type("ProfileContext", (), {})
sys.modules["backend.managers.mgr_profile"] = fake_profile_module

fake_peewee_module = types.ModuleType("peewee")
fake_peewee_module.chunked = lambda items, size: [items]
sys.modules["peewee"] = fake_peewee_module

for module_name in [
    "backend.managers.mgr_rules",
    "backend.database.dao",
    "backend.managers.mgr_profile",
    "peewee",
]:
    sys.modules.pop(module_name, None)

sys.modules["backend.database.dao"] = fake_dao_module
sys.modules["backend.managers.mgr_profile"] = fake_profile_module
sys.modules["peewee"] = fake_peewee_module

mgr_rules_module = importlib.import_module("backend.managers.mgr_rules")
RuleActionType = mgr_rules_module.RuleActionType
RuleManager = mgr_rules_module.RuleManager
RULE_SOURCES = mgr_rules_module.RULE_SOURCES
resolve_import_group_mod_ids = mgr_rules_module._resolve_import_group_mod_ids

for module_name in ("backend.database.dao", "backend.managers.mgr_profile", "peewee"):
    original_module = _ORIGINAL_MODULES[module_name]
    if original_module is None:
        sys.modules.pop(module_name, None)
    else:
        sys.modules[module_name] = original_module


class DummyAtomic:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyDB:
    def atomic(self):
        return DummyAtomic()


class TestRuleManagerDynamicWeights(unittest.TestCase):
    def _make_manager(self, matched_rules=None, mock_save=True):
        manager = RuleManager.__new__(RuleManager)
        manager.context = SimpleNamespace(game_version="1.5.4100")
        manager.builtin_rules = {}
        manager.community_rules = {}
        manager.community_rules_update_time = 0
        manager.user_mod_rules = {}
        manager.user_dynamic_rules = []
        manager.workshop_rules_cache = {}
        manager.settings = {
            "community_mod_rules_enabled": False,
            "user_mod_rules_enabled": False,
            "dynamic_rules_enabled": True,
            "workshop_mod_rules_enabled": False,
            "workshop_rules_as_dependency": False,
            "excluded_community_mods": [],
            "excluded_user_mods": [],
            "excluded_workshop_mods": [],
            "rule_source_priority": RULE_SOURCES,
        }
        manager._save_lock = threading.Lock()
        manager.build_workshop_rules = Mock()
        manager.get_matching_dynamic_rules = Mock(return_value=matched_rules or [])
        if mock_save:
            manager.save_user_rules = Mock()
        return manager

    def _patch_rule_paths(self, user_rules_path: Path, community_rules_path: Path):
        original_user_rules_path = mgr_rules_module.settings.config.user_rules_path
        original_community_rules_path = mgr_rules_module.settings.config.community_rules_path
        mgr_rules_module.settings.config.user_rules_path = str(user_rules_path)
        mgr_rules_module.settings.config.community_rules_path = str(community_rules_path)

        def restore():
            mgr_rules_module.settings.config.user_rules_path = original_user_rules_path
            mgr_rules_module.settings.config.community_rules_path = original_community_rules_path

        self.addCleanup(restore)

    def test_dynamic_weight_set_is_clamped_to_minimum_one(self):
        manager = self._make_manager([
            {"name": "ClampLow", "action": {"type": RuleActionType.WEIGHT_SET, "value": 0}}
        ])

        result = manager.get_effective_mod_rules("mod.test", {"package_id": "mod.test", "mod_type": "Unknown"})

        self.assertEqual(result["weight_info"]["final_weight"], 1)

    def test_dynamic_weight_shift_is_clamped_and_effective_result_stays_below_bottom_anchor(self):
        manager = self._make_manager([
            {"name": "ClampHighShift", "action": {"type": RuleActionType.WEIGHT_SHIFT, "value": 20000}}
        ])

        result = manager.get_effective_mod_rules("mod.test", {"package_id": "mod.test", "mod_type": "Unknown"})

        self.assertEqual(result["weight_info"]["weight_shift"], 999)
        self.assertEqual(result["weight_info"]["final_weight"], 999)

    def test_non_dynamic_special_weight_zero_is_preserved(self):
        manager = self._make_manager([])

        result = manager.get_effective_mod_rules(
            "brrainz.harmony",
            {"package_id": "brrainz.harmony", "mod_type": "Unknown"},
        )

        self.assertEqual(result["weight_info"]["final_weight"], 0)

    def test_dynamic_bottom_uses_position_bottom_anchor(self):
        manager = self._make_manager([
            {"name": "Bottom", "action": {"type": RuleActionType.BOTTOM}}
        ])

        result = manager.get_effective_mod_rules("mod.test", {"package_id": "mod.test", "mod_type": "Unknown"})

        self.assertEqual(result["weight_info"]["final_weight"], 1000)
        self.assertEqual(result["weight_info"]["absolute_type"], "bottom")

    def test_false_absolute_position_value_is_ignored(self):
        manager = self._make_manager([])
        manager.settings["community_mod_rules_enabled"] = True
        manager.community_rules = {"mod.test": {"loadTop": {"value": False}}}

        result = manager.get_effective_mod_rules("mod.test", {"package_id": "mod.test", "mod_type": "Unknown"})

        self.assertEqual(result["weight_info"]["final_weight"], 500)
        self.assertIsNone(result["weight_info"]["absolute_type"])

    def test_upsert_dynamic_rule_sanitizes_out_of_range_values_before_save(self):
        manager = self._make_manager([])

        success = manager.upsert_dynamic_rule(
            {
                "rule_id": "dyn_rule_1",
                "name": "ClampOnSave",
                "action": {"type": RuleActionType.WEIGHT_SET, "value": 0},
            }
        )

        self.assertTrue(success)
        self.assertEqual(manager.user_dynamic_rules[0]["action"]["value"], 1)
        manager.save_user_rules.assert_called_once()

    def test_save_user_rules_uses_configured_path_and_writes_meta(self):
        manager = self._make_manager([], mock_save=False)
        manager.user_mod_rules = {"mod.test": {"loadAfter": {"core.test": {"comment": "test"}}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            user_rules_path = Path(temp_dir) / "custom" / "user_rules.json"
            community_rules_path = Path(temp_dir) / "communityRules.json"
            community_rules_path.write_text("{}", encoding="utf-8")
            self._patch_rule_paths(user_rules_path, community_rules_path)

            success = manager.save_user_rules()

            self.assertTrue(success)
            payload = json.loads(user_rules_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["mod_rules"], manager.user_mod_rules)
            self.assertEqual(payload["meta"]["schema_version"], 1)
            self.assertEqual(payload["meta"]["written_by"], mgr_rules_module.__version__)
            self.assertIsInstance(payload["meta"]["updated_at"], int)

    def test_save_user_rules_propagates_write_failures(self):
        manager = self._make_manager([], mock_save=False)
        manager._write_json_atomic = Mock(side_effect=RuntimeError("boom"))

        with tempfile.TemporaryDirectory() as temp_dir:
            user_rules_path = Path(temp_dir) / "user_rules.json"
            community_rules_path = Path(temp_dir) / "communityRules.json"
            community_rules_path.write_text("{}", encoding="utf-8")
            self._patch_rule_paths(user_rules_path, community_rules_path)

            with self.assertRaises(RuntimeError):
                manager.save_user_rules()

    def test_import_bundle_sanitizes_dynamic_rule_values_and_reports_warnings(self):
        manager = self._make_manager([])
        fake_models_module = types.ModuleType("backend.database.models")
        fake_models_module.db = DummyDB()
        fake_models_module.UserModData = type("UserModData", (), {})
        fake_models_module.GroupData = type("GroupData", (), {"select": staticmethod(lambda: [])})
        fake_models_module.GroupMod = type("GroupMod", (), {})
        fake_models_module.ModAsset = type("ModAsset", (), {})
        fake_models_module.ModInterlock = type("ModInterlock", (), {})

        bundle = {
            "user_rules": {
                "dynamic_rules": [
                    {
                        "rule_id": "dyn_imported",
                        "name": "Imported Rule",
                        "action": {"type": RuleActionType.WEIGHT_SET, "value": 0},
                    }
                ]
            },
            "environment": {},
        }

        original_models_module = sys.modules.get("backend.database.models")
        try:
            sys.modules["backend.database.models"] = fake_models_module
            result = manager.process_import_bundle(bundle)
        finally:
            if original_models_module is not None:
                sys.modules["backend.database.models"] = original_models_module
            else:
                sys.modules.pop("backend.database.models", None)

        self.assertEqual(manager.user_dynamic_rules[0]["action"]["value"], 1)
        self.assertTrue(result["warnings"])

    def test_resolve_import_group_mod_ids_drops_path_hash_like_values(self):
        resolved = resolve_import_group_mod_ids(
            ["deadbeefdeadbeefdeadbeefdeadbeef", "mod.alpha", "DEADBEEFDEADBEEFDEADBEEFDEADBEEF", " ", None],
        )

        self.assertEqual(resolved, ["mod.alpha"])

    def test_load_all_allows_community_rules_without_timestamp_and_still_loads_user_rules(self):
        manager = self._make_manager([], mock_save=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            user_rules_path = Path(temp_dir) / "user_rules.json"
            community_rules_path = Path(temp_dir) / "communityRules.json"
            user_rules_path.write_text(json.dumps({
                "mod_rules": {"mod.test": {"loadAfter": {"core.test": {"comment": "ok"}}}},
                "dynamic_rules": [],
                "settings": {"dynamic_rules_enabled": False},
            }, ensure_ascii=False), encoding="utf-8")
            community_rules_path.write_text(json.dumps({
                "community.mod": {"loadAfter": {"core.test": {"comment": "community"}}}
            }, ensure_ascii=False), encoding="utf-8")
            self._patch_rule_paths(user_rules_path, community_rules_path)

            manager.load_all()

            self.assertIn("mod.test", manager.user_mod_rules)
            self.assertIn("community.mod", manager.community_rules)
            self.assertEqual(manager.community_rules_update_time, 0)
            self.assertFalse(manager.settings["dynamic_rules_enabled"])
            manager.build_workshop_rules.assert_called_once()

    def test_load_all_clears_stale_rules_when_switched_to_missing_user_rules_path(self):
        manager = self._make_manager([], mock_save=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            first_user_rules_path = Path(temp_dir) / "user_rules_a.json"
            second_user_rules_path = Path(temp_dir) / "user_rules_b.json"
            community_rules_path = Path(temp_dir) / "communityRules.json"
            community_rules_path.write_text("{}", encoding="utf-8")
            first_user_rules_path.write_text(json.dumps({
                "mod_rules": {"mod.test": {"loadAfter": {"core.test": {"comment": "ok"}}}},
                "dynamic_rules": [{"rule_id": "dyn_1", "enabled": True}],
                "settings": {"dynamic_rules_enabled": False},
            }, ensure_ascii=False), encoding="utf-8")

            self._patch_rule_paths(first_user_rules_path, community_rules_path)
            manager.load_all()
            self.assertIn("mod.test", manager.user_mod_rules)
            self.assertEqual(len(manager.user_dynamic_rules), 1)

            mgr_rules_module.settings.config.user_rules_path = str(second_user_rules_path)
            manager.load_all()

            self.assertEqual(manager.user_mod_rules, {})
            self.assertEqual(manager.user_dynamic_rules, [])
            self.assertTrue(manager.settings["dynamic_rules_enabled"])

    def test_match_mod_condition_uses_mod_type_fallback(self):
        manager = self._make_manager([])

        matched = manager._match_mod_condition(
            {"package_id": "mod.test", "user_mod_type": None, "mod_type": "LanguagePack"},
            {"field": "mod_type", "operator": "equals", "value": "LanguagePack"},
        )

        self.assertTrue(matched)

    def test_match_mod_condition_supports_not_equals_for_list_fields(self):
        manager = self._make_manager([])

        matched = manager._match_mod_condition(
            {"author": ["Alice", "Bob"]},
            {"field": "author", "operator": "not_equals", "value": "Carol"},
        )
        not_matched = manager._match_mod_condition(
            {"author": ["Alice", "Bob"]},
            {"field": "author", "operator": "not_equals", "value": "Bob"},
        )

        self.assertTrue(matched)
        self.assertFalse(not_matched)

    def test_get_matching_dynamic_rules_respects_priority_order(self):
        manager = self._make_manager([])
        manager.get_matching_dynamic_rules = RuleManager.get_matching_dynamic_rules.__get__(manager, RuleManager)
        manager.user_dynamic_rules = [
            {
                "rule_id": "late_rule",
                "name": "Late Rule",
                "priority": 200,
                "enabled": True,
                "logic": "AND",
                "filters": [{"field": "package_id", "operator": "contains", "value": "mod."}],
            },
            {
                "rule_id": "early_rule",
                "name": "Early Rule",
                "priority": 10,
                "enabled": True,
                "logic": "AND",
                "filters": [{"field": "package_id", "operator": "contains", "value": "mod."}],
            },
        ]

        matched = manager.get_matching_dynamic_rules({"package_id": "mod.test"})

        self.assertEqual([rule["rule_id"] for rule in matched], ["early_rule", "late_rule"])

    def test_upsert_dynamic_rule_normalizes_legacy_user_mod_type_field(self):
        manager = self._make_manager([])

        success = manager.upsert_dynamic_rule(
            {
                "rule_id": "dyn_rule_type_alias",
                "name": "Legacy Type Alias",
                "filters": [{"field": "user_mod_type", "operator": "equals", "value": "XML"}],
                "action": {"type": RuleActionType.WEIGHT_SET, "value": 100},
            }
        )

        self.assertTrue(success)
        self.assertEqual(manager.user_dynamic_rules[0]["filters"][0]["field"], "mod_type")

    def test_match_mod_condition_name_only_checks_raw_name(self):
        manager = self._make_manager([])

        matched_raw = manager._match_mod_condition(
            {"name": "Harmony", "alias_name": "和谐前置"},
            {"field": "name", "operator": "equals", "value": "Harmony"},
        )
        not_matched_alias = manager._match_mod_condition(
            {"name": "Harmony", "alias_name": "和谐前置"},
            {"field": "name", "operator": "equals", "value": "和谐前置"},
        )

        self.assertTrue(matched_raw)
        self.assertFalse(not_matched_alias)

    def test_match_mod_condition_alias_name_checks_alias_and_raw_name(self):
        manager = self._make_manager([])

        matched_alias = manager._match_mod_condition(
            {"name": "Harmony", "alias_name": "和谐前置"},
            {"field": "alias_name", "operator": "equals", "value": "和谐前置"},
        )
        matched_raw = manager._match_mod_condition(
            {"name": "Harmony", "alias_name": "和谐前置"},
            {"field": "alias_name", "operator": "equals", "value": "Harmony"},
        )

        self.assertTrue(matched_alias)
        self.assertTrue(matched_raw)

    def test_match_mod_condition_list_field_matches_any_item(self):
        manager = self._make_manager([])

        matched_author = manager._match_mod_condition(
            {"author": ["Alice", "Bob"]},
            {"field": "author", "operator": "equals", "value": "Bob"},
        )
        matched_group = manager._match_mod_condition(
            {"groups": ["前置库", "UI"]},
            {"field": "groups", "operator": "contains", "value": "ui"},
        )

        self.assertTrue(matched_author)
        self.assertTrue(matched_group)


if __name__ == "__main__":
    unittest.main()
