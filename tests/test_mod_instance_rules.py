import unittest


class FakeRuleManager:
    def __init__(self):
        self.calls = []

    def get_effective_mod_rules(self, mod_id, mod_full_data):
        self.calls.append((mod_id, mod_full_data["source"]))
        native_targets = [rule["package_id"] for rule in mod_full_data.get("load_after_mods", [])]
        return {
            "dependencies": [],
            "load_after": [
                *[
                    {"target_id": target, "source": {"type": "native"}}
                    for target in native_targets
                ],
                {"target_id": "external.shared", "source": {"type": "user"}},
            ],
            "load_before": [],
            "incompatible": [],
            "weight_info": {},
        }


class TestModInstanceRules(unittest.TestCase):
    def test_select_mod_instance_drops_stale_steam_token_without_workshop_variant(self):
        from backend.load_order.package_tokens import select_mod_instance

        selected = select_mod_instance(
            {"package_id": "shared.mod", "source": "local"},
            "shared.mod_steam",
        )

        self.assertEqual(selected["active_package_token"], "shared.mod")
        self.assertEqual(selected["source_preference"], "local")
        self.assertFalse(selected["is_coexistence"])

    def test_resolve_effective_rules_uses_mod_package_id_when_token_is_empty(self):
        from types import SimpleNamespace

        from backend.managers.mgr_rules import RuleManager

        manager = object.__new__(RuleManager)
        manager.builtin_rules = {}
        manager.community_rules = {}
        manager.user_mod_rules = {
            "shared.mod": {
                "rules": {
                    "loadAfter": {"external.shared": {"comment": "shared rule"}},
                },
            },
        }
        manager.user_dynamic_rules = []
        manager.workshop_rules_cache = {}
        manager.context = SimpleNamespace(game_version="1.5.4069")
        manager.settings = manager._build_default_settings()

        _, rules = manager.resolve_effective_mod_rules("", {"package_id": "shared.mod"})

        self.assertIn("external.shared", [rule["target_id"] for rule in rules["load_after"]])

    def test_coexist_workshop_variant_gets_own_native_rules_and_shared_external_rules(self):
        from backend.api import _attach_effective_rules_to_mod_instances

        rule_mgr = FakeRuleManager()
        mod = {
            "package_id": "shared.mod",
            "source": "local",
            "load_after_mods": [{"package_id": "local.dep"}],
            "coexist_workshop_variant": {
                "package_id": "shared.mod",
                "source": "workshop",
                "load_after_mods": [{"package_id": "workshop.dep"}],
            },
        }

        _attach_effective_rules_to_mod_instances([mod], rule_mgr)

        local_targets = [rule["target_id"] for rule in mod["rules"]["load_after"]]
        workshop_targets = [
            rule["target_id"]
            for rule in mod["coexist_workshop_variant"]["rules"]["load_after"]
        ]
        self.assertEqual(rule_mgr.calls, [("shared.mod", "local"), ("shared.mod", "workshop")])
        self.assertIn("local.dep", local_targets)
        self.assertNotIn("workshop.dep", local_targets)
        self.assertIn("workshop.dep", workshop_targets)
        self.assertNotIn("local.dep", workshop_targets)
        self.assertIn("external.shared", local_targets)
        self.assertIn("external.shared", workshop_targets)

    def test_preferred_steam_token_selects_workshop_variant_for_canonical_mod_map(self):
        from backend.api import _build_mod_map_for_load_order_tokens

        mods = [{
            "package_id": "shared.mod",
            "source": "local",
            "coexist_workshop_variant": {
                "package_id": "shared.mod",
                "source": "workshop",
            },
        }]

        mod_map = _build_mod_map_for_load_order_tokens(mods, {"shared.mod": "shared.mod_steam"})

        self.assertEqual(mod_map["shared.mod"]["source"], "workshop")

    def test_language_pack_ownership_keeps_local_and_workshop_results_separate(self):
        from backend.load_order.language_pack_ownership import resolve_language_pack_ownership_for_mods

        mods = [{
            "package_id": "translation.pack",
            "mod_type": "LanguagePack",
            "dependencies_mods": [{"package_id": "local.owner"}],
            "coexist_workshop_variant": {
                "package_id": "translation.pack",
                "mod_type": "LanguagePack",
                "dependencies_mods": [{"package_id": "workshop.owner"}],
            },
        }]

        owner_map = resolve_language_pack_ownership_for_mods(mods)

        self.assertEqual(owner_map["translation.pack"]["owners"], [{"package_id": "local.owner"}])
        self.assertEqual(owner_map["translation.pack_steam"]["owners"], [{"package_id": "workshop.owner"}])

    def test_export_dependency_expansion_uses_selected_workshop_instance(self):
        from backend.managers.mgr_mod_package import ModPackageManager

        manager = object.__new__(ModPackageManager)
        mods = [{
            "package_id": "shared.mod",
            "rules": {"dependencies": [{"target_id": "local.dep"}]},
            "coexist_workshop_variant": {
                "package_id": "shared.mod",
                "rules": {"dependencies": [{"target_id": "workshop.dep"}]},
            },
        }]

        result = manager._expand_mod_ids(
            ["shared.mod_steam"],
            mods,
            active_token_set={"shared.mod_steam"},
            include_dependencies=True,
        )

        self.assertEqual(result, ["shared.mod_steam", "workshop.dep"])

    def test_export_bare_token_keeps_local_instance_even_when_workshop_is_newer(self):
        from backend.load_order.package_tokens import parse_package_token
        from backend.managers.mgr_mod_package import ModPackageManager

        manager = object.__new__(ModPackageManager)
        mod = {
            "package_id": "shared.mod",
            "source": "local",
            "file_modify_time": 1,
            "coexist_workshop_variant": {
                "package_id": "shared.mod",
                "source": "workshop",
                "file_modify_time": 999,
            },
        }

        chosen = manager._select_export_asset(mod, parse_package_token("shared.mod"), set())

        self.assertEqual(chosen["source"], "local")

    def test_ai_rule_query_uses_workshop_instance_for_steam_token(self):
        from unittest.mock import patch

        from backend.ai.ai_tools import AIToolExecutor, GetModRulesArgs

        executor = object.__new__(AIToolExecutor)
        executor.context = object()
        visible_mod = {
            "package_id": "shared.mod",
            "dependencies_mods": [{"package_id": "local.dep"}],
            "coexist_workshop_variant": {
                "dependencies_mods": [{"package_id": "workshop.dep"}],
            },
        }

        with patch("backend.ai.ai_tools.ModDAO.get_visible_profile_mod", return_value=visible_mod):
            result = executor._tool_get_mod_rules(GetModRulesArgs(package_id="shared.mod_steam", native_only=True))

        self.assertEqual(result["dependencies"], [{"package_id": "workshop.dep"}])


if __name__ == "__main__":
    unittest.main()
