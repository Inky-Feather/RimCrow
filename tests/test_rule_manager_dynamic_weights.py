import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


fake_dao_module = types.ModuleType("backend.database.dao")
fake_dao_module.ModDAO = Mock()
fake_dao_module.GroupDAO = Mock()
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


class DummyAtomic:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyDB:
    def atomic(self):
        return DummyAtomic()


class TestRuleManagerDynamicWeights(unittest.TestCase):
    def _make_manager(self, matched_rules=None):
        manager = RuleManager.__new__(RuleManager)
        manager.context = SimpleNamespace(game_version="1.5.4100")
        manager.builtin_rules = {}
        manager.community_rules = {}
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
        manager.get_matching_dynamic_rules = Mock(return_value=matched_rules or [])
        manager.save_user_rules = Mock()
        return manager

    def test_dynamic_weight_set_is_clamped_to_minimum_one(self):
        manager = self._make_manager([
            {"name": "ClampLow", "action": {"type": RuleActionType.WEIGHT_SET, "value": 0}}
        ])

        result = manager.get_effective_mod_rules("mod.test", {"package_id": "mod.test", "mod_type": "Unknown"})

        self.assertEqual(result["weight_info"]["final_weight"], 1)

    def test_dynamic_weight_shift_is_clamped_and_effective_result_stays_below_10000(self):
        manager = self._make_manager([
            {"name": "ClampHighShift", "action": {"type": RuleActionType.WEIGHT_SHIFT, "value": 20000}}
        ])

        result = manager.get_effective_mod_rules("mod.test", {"package_id": "mod.test", "mod_type": "Unknown"})

        self.assertEqual(result["weight_info"]["weight_shift"], 9999)
        self.assertEqual(result["weight_info"]["final_weight"], 9999)

    def test_non_dynamic_special_weight_zero_is_preserved(self):
        manager = self._make_manager([])

        result = manager.get_effective_mod_rules(
            "brrainz.harmony",
            {"package_id": "brrainz.harmony", "mod_type": "Unknown"},
        )

        self.assertEqual(result["weight_info"]["final_weight"], 0)

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


if __name__ == "__main__":
    unittest.main()
