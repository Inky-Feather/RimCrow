import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

fake_dao_module = types.ModuleType("backend.database.dao")
fake_dao_module.ModDAO = Mock()
fake_dao_module.GroupDAO = Mock()
sys.modules.setdefault("backend.database.dao", fake_dao_module)

fake_models_module = types.ModuleType("backend.database.models")
fake_models_module.ModInterlock = type("ModInterlock", (), {})
sys.modules.setdefault("backend.database.models", fake_models_module)

fake_profile_module = types.ModuleType("backend.managers.mgr_profile")
fake_profile_module.ProfileContext = type("ProfileContext", (), {})
sys.modules.setdefault("backend.managers.mgr_profile", fake_profile_module)

fake_rules_module = types.ModuleType("backend.managers.mgr_rules")
fake_rules_module.RuleManager = type("RuleManager", (), {"__init__": lambda self, context: None})
sys.modules.setdefault("backend.managers.mgr_rules", fake_rules_module)

import backend.managers.mgr_sorter as mgr_sorter_module
from backend.managers.mgr_sorter import AtomicGroup, OrderSorter


class TestOrderSorterStrategies(unittest.TestCase):
    def setUp(self):
        self.sorter = OrderSorter(SimpleNamespace(game_version="1.5.4100"))
        self.sorter.rule_mgr = Mock()

    def _run_sort(self, strategy, mods_data, rules_map, groups, adj, config_overrides=None):
        self.sorter.rule_mgr.get_effective_mod_rules.side_effect = lambda mod_id, mod_data: rules_map[mod_id]
        config = {
            "auto_sort_strategy": strategy,
            "enable_tool_mods": False,
            "auto_activate_dependencies": False,
            "sort_mods_by": "name",
            "language_packs_follow_targets": False,
        }
        if config_overrides:
            config.update(config_overrides)

        with patch.object(mgr_sorter_module.ModDAO, "get_profile_mods", return_value=mods_data), \
             patch.object(fake_dao_module.GroupDAO, "get_groups_structured_by_mod_ids", return_value=[]), \
             patch.object(self.sorter, "build_atomic_groups", return_value=(groups, [])), \
             patch.object(self.sorter, "_build_weighted_graph", return_value=(adj, {})), \
             patch.object(self.sorter, "_break_cycles", return_value=[]), \
             patch.object(mgr_sorter_module.settings, "config", SimpleNamespace(**config)):
            return self.sorter.sort([m["package_id"] for m in mods_data])

    def test_unknown_strategy_falls_back_to_classic_sort_logic(self):
        groups = [AtomicGroup(["mod.a"])]
        result = self._run_sort(
            "unknown",
            [{"package_id": "mod.a", "name": "A"}],
            {"mod.a": {"weight_info": {"final_weight": 500, "absolute_type": None}}},
            groups,
            {},
        )
        self.assertEqual(result["strategy"], "classic_sort_logic")

    def test_classic_sort_logic_group_weight_keeps_bottom_member_conservative(self):
        groups = [AtomicGroup(["mod.bottom", "mod.framework"]), AtomicGroup(["mod.normal"])]
        result = self._run_sort(
            "classic_sort_logic",
            [
                {"package_id": "mod.bottom", "name": "Bottom"},
                {"package_id": "mod.framework", "name": "Framework"},
                {"package_id": "mod.normal", "name": "Normal"},
            ],
            {
                "mod.bottom": {"weight_info": {"final_weight": 1000, "absolute_type": "bottom"}},
                "mod.framework": {"weight_info": {"final_weight": 150, "absolute_type": None}},
                "mod.normal": {"weight_info": {"final_weight": 500, "absolute_type": None}},
            },
            groups,
            {},
        )
        self.assertEqual(result["sorted_ids"], ["mod.bottom", "mod.framework", "mod.normal"])

    def test_edge_push_strategy_pushes_bottom_group_toward_end(self):
        groups = [AtomicGroup(["mod.bottom", "mod.framework"]), AtomicGroup(["mod.normal"])]
        result = self._run_sort(
            "edge_enhanced_sort_logic",
            [
                {"package_id": "mod.bottom", "name": "Bottom"},
                {"package_id": "mod.framework", "name": "Framework"},
                {"package_id": "mod.normal", "name": "Normal"},
            ],
            {
                "mod.bottom": {"weight_info": {"final_weight": 1000, "absolute_type": "bottom"}},
                "mod.framework": {"weight_info": {"final_weight": 150, "absolute_type": None}},
                "mod.normal": {"weight_info": {"final_weight": 500, "absolute_type": None}},
            },
            groups,
            {},
        )
        self.assertEqual(result["sorted_ids"], ["mod.normal", "mod.bottom", "mod.framework"])

    def test_classic_sort_logic_propagation_keeps_old_light_successor_tendency(self):
        group_a = AtomicGroup(["mod.a"])
        group_b = AtomicGroup(["mod.b"])
        group_c = AtomicGroup(["mod.c"])
        groups = [group_a, group_b, group_c]
        adj = {id(group_a): {id(group_c): 1}}
        result = self._run_sort(
            "classic_sort_logic",
            [
                {"package_id": "mod.a", "name": "A"},
                {"package_id": "mod.b", "name": "B"},
                {"package_id": "mod.c", "name": "C"},
            ],
            {
                "mod.a": {"weight_info": {"final_weight": 900, "absolute_type": None}},
                "mod.b": {"weight_info": {"final_weight": 700, "absolute_type": None}},
                "mod.c": {"weight_info": {"final_weight": 500, "absolute_type": None}},
            },
            groups,
            adj,
        )
        self.assertEqual(result["sorted_ids"], ["mod.a", "mod.c", "mod.b"])

    def test_edge_push_top_chain_prefers_shorter_head_at_top(self):
        group_a = AtomicGroup(["mod.a"])
        group_top_short = AtomicGroup(["mod.top.short"])
        group_b = AtomicGroup(["mod.b"])
        group_c = AtomicGroup(["mod.c"])
        group_top_long = AtomicGroup(["mod.top.long"])
        groups = [group_a, group_top_short, group_b, group_c, group_top_long]
        adj = {
            id(group_a): {id(group_top_short): 1},
            id(group_b): {id(group_c): 1},
            id(group_c): {id(group_top_long): 1},
        }
        result = self._run_sort(
            "edge_enhanced_sort_logic",
            [
                {"package_id": "mod.a", "name": "A"},
                {"package_id": "mod.top.short", "name": "TopShort"},
                {"package_id": "mod.b", "name": "B"},
                {"package_id": "mod.c", "name": "C"},
                {"package_id": "mod.top.long", "name": "TopLong"},
            ],
            {
                "mod.a": {"weight_info": {"final_weight": 500, "absolute_type": None}},
                "mod.top.short": {"weight_info": {"final_weight": 0, "absolute_type": "top"}},
                "mod.b": {"weight_info": {"final_weight": 700, "absolute_type": None}},
                "mod.c": {"weight_info": {"final_weight": 500, "absolute_type": None}},
                "mod.top.long": {"weight_info": {"final_weight": 0, "absolute_type": "top"}},
            },
            groups,
            adj,
        )
        self.assertEqual(result["sorted_ids"], ["mod.a", "mod.top.short", "mod.b", "mod.c", "mod.top.long"])

    def test_edge_push_bottom_chain_prefers_shorter_tail_at_bottom(self):
        group_bottom_short = AtomicGroup(["mod.bottom.short"])
        group_x = AtomicGroup(["mod.x"])
        group_bottom_long = AtomicGroup(["mod.bottom.long"])
        group_y = AtomicGroup(["mod.y"])
        group_z = AtomicGroup(["mod.z"])
        groups = [group_bottom_short, group_x, group_bottom_long, group_y, group_z]
        adj = {
            id(group_bottom_short): {id(group_x): 1},
            id(group_bottom_long): {id(group_y): 1},
            id(group_y): {id(group_z): 1},
        }
        result = self._run_sort(
            "edge_enhanced_sort_logic",
            [
                {"package_id": "mod.bottom.short", "name": "BottomShort"},
                {"package_id": "mod.x", "name": "X"},
                {"package_id": "mod.bottom.long", "name": "BottomLong"},
                {"package_id": "mod.y", "name": "Y"},
                {"package_id": "mod.z", "name": "Z"},
            ],
            {
                "mod.bottom.short": {"weight_info": {"final_weight": 1000, "absolute_type": "bottom"}},
                "mod.x": {"weight_info": {"final_weight": 500, "absolute_type": None}},
                "mod.bottom.long": {"weight_info": {"final_weight": 1000, "absolute_type": "bottom"}},
                "mod.y": {"weight_info": {"final_weight": 500, "absolute_type": None}},
                "mod.z": {"weight_info": {"final_weight": 500, "absolute_type": None}},
            },
            groups,
            adj,
        )
        self.assertEqual(result["sorted_ids"], ["mod.bottom.long", "mod.y", "mod.z", "mod.bottom.short", "mod.x"])

    def test_edge_push_keeps_non_edge_nodes_close_to_classic_order(self):
        group_alpha = AtomicGroup(["mod.alpha"])
        group_zeta = AtomicGroup(["mod.zeta"])
        group_c = AtomicGroup(["mod.c"])
        group_e = AtomicGroup(["mod.e"])
        groups = [group_alpha, group_zeta, group_c, group_e]
        adj = {
            id(group_alpha): {id(group_c): 1},
            id(group_zeta): {id(group_e): 1},
        }
        mods_data = [
            {"package_id": "mod.alpha", "name": "Alpha"},
            {"package_id": "mod.zeta", "name": "Zeta"},
            {"package_id": "mod.c", "name": "C"},
            {"package_id": "mod.e", "name": "E"},
        ]
        rules_map = {
            "mod.alpha": {"weight_info": {"final_weight": 900, "absolute_type": None}},
            "mod.zeta": {"weight_info": {"final_weight": 700, "absolute_type": None}},
            "mod.c": {"weight_info": {"final_weight": 500, "absolute_type": None}},
            "mod.e": {"weight_info": {"final_weight": 500, "absolute_type": None}},
        }

        classic_result = self._run_sort("classic_sort_logic", mods_data, rules_map, groups, adj)
        edge_result = self._run_sort("edge_enhanced_sort_logic", mods_data, rules_map, groups, adj)

        self.assertEqual(classic_result["sorted_ids"], ["mod.alpha", "mod.c", "mod.zeta", "mod.e"])
        self.assertEqual(edge_result["sorted_ids"], classic_result["sorted_ids"])

    def test_edge_push_overlap_node_keeps_normal_weight_and_warns(self):
        group_bottom = AtomicGroup(["mod.bottom"])
        group_shared = AtomicGroup(["mod.shared"])
        group_top = AtomicGroup(["mod.top"])
        groups = [group_bottom, group_shared, group_top]
        adj = {
            id(group_bottom): {id(group_shared): 1},
            id(group_shared): {id(group_top): 1},
        }
        result = self._run_sort(
            "edge_enhanced_sort_logic",
            [
                {"package_id": "mod.bottom", "name": "Bottom"},
                {"package_id": "mod.shared", "name": "Shared"},
                {"package_id": "mod.top", "name": "Top"},
            ],
            {
                "mod.bottom": {"weight_info": {"final_weight": 1000, "absolute_type": "bottom"}},
                "mod.shared": {"weight_info": {"final_weight": 500, "absolute_type": None}},
                "mod.top": {"weight_info": {"final_weight": 0, "absolute_type": "top"}},
            },
            groups,
            adj,
        )

        self.assertEqual(result["sorted_ids"], ["mod.bottom", "mod.shared", "mod.top"])
        self.assertTrue(any(w["type"] == "edge_closure_conflict" for w in result["warnings"]))

    def test_edge_push_queue_key_handles_conflicting_anchor_group_without_type_error(self):
        group_mixed = AtomicGroup(["mod.top.anchor", "mod.bottom.anchor"])
        group_promoted_top = AtomicGroup(["mod.top.only"])
        groups = [group_mixed, group_promoted_top]
        adj = {
            id(group_mixed): {id(group_promoted_top): 1},
        }
        result = self._run_sort(
            "edge_enhanced_sort_logic",
            [
                {"package_id": "mod.top.anchor", "name": "MixedTop"},
                {"package_id": "mod.bottom.anchor", "name": "MixedBottom"},
                {"package_id": "mod.top.only", "name": "TopOnly"},
            ],
            {
                "mod.top.anchor": {"weight_info": {"final_weight": 0, "absolute_type": "top"}},
                "mod.bottom.anchor": {"weight_info": {"final_weight": 1000, "absolute_type": "bottom"}},
                "mod.top.only": {"weight_info": {"final_weight": 0, "absolute_type": "top"}},
            },
            groups,
            adj,
        )

        self.assertEqual(result["sorted_ids"], ["mod.top.anchor", "mod.bottom.anchor", "mod.top.only"])
        self.assertTrue(any(w["type"] == "edge_anchor_conflict" for w in result["warnings"]))

    def test_language_pack_follow_targets_can_pull_pack_up_to_last_predecessor(self):
        group_core = AtomicGroup(["mod.core"])
        group_unrelated = AtomicGroup(["mod.unrelated"])
        group_lang = AtomicGroup(["mod.lang"])
        groups = [group_core, group_unrelated, group_lang]
        adj = {
            id(group_core): {id(group_lang): 1},
        }
        result = self._run_sort(
            "classic_sort_logic",
            [
                {"package_id": "mod.core", "name": "Core", "mod_type": "XML"},
                {"package_id": "mod.unrelated", "name": "Unrelated", "mod_type": "XML"},
                {"package_id": "mod.lang", "name": "Lang", "mod_type": "LanguagePack"},
            ],
            {
                "mod.core": {
                    "weight_info": {"final_weight": 500, "absolute_type": None},
                    "dependencies": [],
                    "load_after": [],
                    "load_before": [],
                },
                "mod.unrelated": {
                    "weight_info": {"final_weight": 500, "absolute_type": None},
                    "dependencies": [],
                    "load_after": [],
                    "load_before": [],
                },
                "mod.lang": {
                    "weight_info": {"final_weight": 900, "absolute_type": None},
                    "dependencies": [],
                    "load_after": [{"target_id": "mod.core"}],
                    "load_before": [],
                },
            },
            groups,
            adj,
            {"language_packs_follow_targets": True},
        )

        self.assertEqual(result["sorted_ids"], ["mod.core", "mod.lang", "mod.unrelated"])

    def test_language_pack_follow_targets_warns_when_successor_blocks_move(self):
        group_core = AtomicGroup(["mod.core"])
        group_blocker = AtomicGroup(["mod.blocker"])
        group_lang = AtomicGroup(["mod.lang"])
        groups = [group_core, group_blocker, group_lang]
        adj = {
            id(group_core): {id(group_lang): 1},
            id(group_blocker): {id(group_lang): 1},
        }
        result = self._run_sort(
            "classic_sort_logic",
            [
                {"package_id": "mod.core", "name": "ACore", "mod_type": "XML"},
                {"package_id": "mod.blocker", "name": "Blocker", "mod_type": "XML"},
                {"package_id": "mod.lang", "name": "Lang", "mod_type": "LanguagePack"},
            ],
            {
                "mod.core": {
                    "weight_info": {"final_weight": 500, "absolute_type": None},
                    "dependencies": [],
                    "load_after": [],
                    "load_before": [],
                },
                "mod.blocker": {
                    "weight_info": {"final_weight": 500, "absolute_type": None},
                    "dependencies": [],
                    "load_after": [],
                    "load_before": [],
                },
                "mod.lang": {
                    "weight_info": {"final_weight": 900, "absolute_type": None},
                    "dependencies": [],
                    "load_after": [{"target_id": "mod.core"}],
                    "load_before": [],
                },
            },
            groups,
            adj,
            {"language_packs_follow_targets": True},
        )

        self.assertEqual(result["sorted_ids"], ["mod.core", "mod.blocker", "mod.lang"])
        self.assertTrue(any(w["type"] == "language_pack_follow_blocked" for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
