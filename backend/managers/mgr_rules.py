import os
import json
import re
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.utils.logger import logger
from backend.database.dao import ModDAO, GroupDAO
from backend.settings import RULES_DIR, USER_RULES_PATH, settings

class RuleActionType:
    WEIGHT_SET = "weight_set"       # 强制设置权重 (0-1000)
    WEIGHT_SHIFT = "weight_shift"   # 权重偏移 (如 -50)
    LOAD_AFTER = "load_after"       # 必须在某ID后
    LOAD_BEFORE = "load_before"     # 必须在某ID前
    TOP = "top"                     # 置顶 (权重设为0)
    BOTTOM = "bottom"               # 置底 (权重设为1000)
class RuleManager:
    def __init__(self):
        # 内存中的规则缓存
        self.community_rules: Dict[str, Any] = {}
        self.user_mod_rules: Dict[str, Any] = {}
        self.user_dynamic_rules: List[Dict[str, Any]] = []
        self.settings = {
            "community_mod_rules_enabled": True,    # 全局社区规则总开关
            "user_mod_rules_enabled": True,     # 全局用户单项规则总开关
            "dynamic_rules_enabled": True,      # 全局动态规则总开关
            "excluded_community_mods": [],      # 被禁用的社区 Mod ID 列表 (黑名单)
            "excluded_user_mods": []            # 被禁用的用户 Mod ID 列表 (黑名单)
        }
        # 确保目录存在
        RULES_DIR.mkdir(parents=True, exist_ok=True)
        self.load_all()

    def load_all(self):
        """核心：从磁盘加载所有规则数据"""
        try:
            # 加载社区规则
            community_file_path = Path(settings.config.community_rules_path)
            if community_file_path.exists():
                with open(community_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 兼容不同格式，有些可能是 { "rules": {...} }，有些直接是 {...}
                    self.community_rules = data.get("rules", data)
                    
            # 加载用户规则
            user_file_path = Path(settings.config.user_rules_path)
            if user_file_path.exists():
                with open(user_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.user_mod_rules = data.get("mod_rules", {})
                    self.user_dynamic_rules = data.get("dynamic_rules", [])
                    # 加载设置
                    self.settings.update(data.get("settings", {}))
        except Exception as e:
            logger.error(f"Failed to load rules: {e}")
            # 出错时保持空状态，不中断启动

    def save_user_rules(self):
        """持久化用户规则"""
        try:
            data = {
                "settings": self.settings, # 保存设置
                "mod_rules": self.user_mod_rules,
                "dynamic_rules": self.user_dynamic_rules
            }
            with open(USER_RULES_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save user rules: {e}")
            
    # =========================================================================
    # 0. 开关控制逻辑 (Professional Toggle Logic)
    # =========================================================================

    def set_global_setting(self, key: str, value: Any):
        """设置全局开关 (例如 community_mod_rules_enabled)"""
        if key in self.settings:
            self.settings[key] = value
            self.save_user_rules()
            return True
        return False

    def toggle_user_mod_rule_exclusion(self, package_id: str, exclude: bool):
        """单独禁用/启用某个 Mod 的所有用户规则 (黑名单操作)"""
        pid = package_id.lower().strip()
        excluded_list = self.settings["excluded_user_mods"]
        if exclude and pid not in excluded_list:
            excluded_list.append(pid)
        elif not exclude and pid in excluded_list:
            excluded_list.remove(pid)
        self.save_user_rules()
        return True

    def toggle_community_mod_exclusion(self, package_id: str, exclude: bool):
        """将某个 Mod 加入/移出社区规则黑名单"""
        pid = package_id.lower().strip()
        excluded_list = self.settings["excluded_community_mods"]
        if exclude and pid not in excluded_list:
            excluded_list.append(pid)
        elif not exclude and pid in excluded_list:
            excluded_list.remove(pid)
        self.save_user_rules()
        return True
    
    def collect_constraints(self, mod_id: str, mod_full_data: dict) -> List[Dict]:
        """
        核心聚合函数：根据当前的【全局开关】和【黑名单】，返回该 Mod 生效的全部约束
        """
        mid_l = mod_id.lower()
        all_res = []

        # 1. 原生规则 (About.xml) - 永远不受开关影响
        for p in mod_full_data.get('dependencies_mods', []):
            all_res.append({"target": p['package_id'].lower(), "type": "after", "source": {"name": "原生依赖", "type": "native"}})
        for p in mod_full_data.get('load_after_mods', []):
            all_res.append({"target": p.lower(), "type": "after", "source": {"name": "原生前置", "type": "native"}})
        for p in mod_full_data.get('load_before_mods', []):
            all_res.append({"target": p.lower(), "type": "before", "source": {"name": "原生后置", "type": "native"}})
        for p in mod_full_data.get('incompatible_mods', []):
            all_res.append({"target": p.lower(), "type": "incompatible", "source": {"name": "原生冲突", "type": "native"}})

        # 2. 社区规则 (Community Rules)
        if self.settings.get("community_mod_rules_enabled", True):  # 全局开关
            if mid_l not in self.settings.get("excluded_community_mods", []): # 黑名单过滤
                comm = self.community_rules.get(mid_l, {})
                for t, info in comm.get("loadAfter", {}).items():
                    all_res.append({"target": t.lower(), "type": "after", "source": {"name": "社区规则", "type": "community", "info": info}})
                for t, info in comm.get("loadBefore", {}).items():
                    all_res.append({"target": t.lower(), "type": "before", "source": {"name": "社区规则", "type": "community", "info": info}})
                for t, info in comm.get("incompatibleWith", {}).items():
                    all_res.append({"target": t.lower(), "type": "incompatible", "source": {"name": "社区规则", "type": "community", "info": info}})

        # 3. 用户单项规则 (User Single Rules)
        if self.settings.get("user_mod_rules_enabled", True): # 全局开关
            user_entry = self.user_mod_rules.get(mid_l, {})
            # 校验单项开关
            is_enabled = not mid_l in self.settings.get("excluded_user_mods", [])
            if is_enabled:
                rules = user_entry["rules"] if isinstance(user_entry, dict) and "rules" in user_entry else user_entry
                for t, info in rules.get("loadAfter", {}).items():
                    all_res.append({"target": t.lower(), "type": "after", "source": {"name": "用户规则", "type": "user", "info": info}})
                for t, info in rules.get("loadBefore", {}).items():
                    all_res.append({"target": t.lower(), "type": "before", "source": {"name": "用户规则", "type": "user", "info": info}})
                for t, info in rules.get("incompatibleWith", {}).items():
                    all_res.append({"target": t.lower(), "type": "incompatible", "source": {"name": "用户规则", "type": "user", "info": info}})

        # 4. 动态规则 (Dynamic Rules)
        if self.settings.get("dynamic_rules_enabled", True): # 全局开关
            matched_dyn = self.get_matching_dynamic_rules(mod_full_data)
            for rule in matched_dyn:
                act = rule.get("action", {})
                # 这里不仅返回先后顺序，还要返回权重操作
                all_res.append({
                    "type": "dynamic",
                    "action": act,
                    "rule_name": rule['name']
                })

        return all_res

    def _parse_static_rules(self, content: dict, source: str) -> List[Dict]:
        """解析 loadAfter/loadBefore 结构"""
        res = []
        for r_type in ["loadAfter", "loadBefore", "incompatibleWith"]:
            if r_type in content:
                for target_id, info in content[r_type].items():
                    res.append({
                        "type": r_type,
                        "target": target_id.lower(),
                        "source": source,
                        "info": info
                    })
        return res

    # =========================================================================
    # 1. 规则 CRUD (核心逻辑)
    # =========================================================================

    def update_user_mod_rule(self, package_id: str, rule_content: dict):
        """新增或修改某个具体 Mod 的先后/冲突规则"""
        pid = package_id.lower().strip()
        # rule_content 结构: {"loadAfter": {...}, "loadBefore": {...}, "incompatibleWith": {...}}
        self.user_mod_rules[pid] = rule_content
        self.save_user_rules()
        return True

    def delete_user_mod_rule(self, package_id: str):
        """删除某个 Mod 的所有自定义单项规则"""
        pid = package_id.lower().strip()
        if pid in self.user_mod_rules:
            del self.user_mod_rules[pid]
            self.save_user_rules()
        return True

    def upsert_dynamic_rule(self, rule_obj: dict):
        """新增或更新动态规则"""
        rid = rule_obj.get('rule_id')
        if not rid: return False
        # 查找是否存在
        idx = next((i for i, r in enumerate(self.user_dynamic_rules) if r['rule_id'] == rid), -1)
        if idx > -1:
            self.user_dynamic_rules[idx] = rule_obj
        else:
            self.user_dynamic_rules.append(rule_obj)
        self.save_user_rules()
        return True

    def delete_dynamic_rule(self, rule_id: str):
        """物理删除动态规则"""
        self.user_dynamic_rules = [r for r in self.user_dynamic_rules if r['rule_id'] != rule_id]
        self.save_user_rules()
        return True

    def toggle_dynamic_rule(self, rule_id: str, enabled: bool):
        """仅切换启用状态"""
        for r in self.user_dynamic_rules:
            if r['rule_id'] == rule_id:
                r['enabled'] = enabled
                break
        self.save_user_rules()
        return True

    def overwrite_community_rules(self, raw_json: str):
        """更新社区规则库"""
        try:
            # 尝试解析，确保格式正确
            data = json.loads(raw_json)
            with open(settings.config.community_rules_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.load_all()
            return True
        except Exception as e:
            logger.error(f"Failed to update community rules: {e}")
            raise e

    # =========================================================================
    # 2. 匹配与查询 (Engine)
    # =========================================================================

    def _match_mod_condition(self, mod_data: dict, filter_item: dict) -> bool:
        """
        判断一个 Mod 是否满足某项过滤条件
        mod_data: 包含基础 Mod 信息和 UserModData 的合并字典
        """
        field = filter_item.get("field")
        op = filter_item.get("operator")
        target = str(filter_item.get("value", "")).lower()
        # 获取实际值，支持点分语法 (例如 metadata.author)
        actual = mod_data.get(field)

        if actual is None: return False
        
        # 统一转为字符串列表进行匹配
        if isinstance(actual, list):
            actual_strs = [str(i).lower() for i in actual]
        else:
            actual_strs = [str(actual).lower()]

        try:
            if op == "equals": return any(target == s for s in actual_strs)
            if op == "contains": return any(target in s for s in actual_strs)
            if op == "not_contains": return not any(target in s for s in actual_strs)
            if op == "starts_with": return any(s.startswith(target) for s in actual_strs)
            if op == "ends_with": return any(s.endswith(target) for s in actual_strs)
            if op == "regex": return any(re.search(target, s, re.IGNORECASE) for s in actual_strs)
        except Exception:
            return False # 正则错误等情况
        return False

    def get_matching_dynamic_rules(self, mod_data: dict) -> List[dict]:
        """获取适用于该 Mod 的所有动态规则"""
        matched = []
        for rule in self.user_dynamic_rules:
            if not rule.get("enabled", True): continue
            logic = rule.get("logic", "AND")
            filters = rule.get("filters", [])
            if not filters: continue # 无条件的规则不生效
            results = [self._match_mod_condition(mod_data, f) for f in filters]
            is_match = all(results) if logic == "AND" else any(results)
            if is_match: matched.append(rule)
        return matched

    # =========================================================================
    # 3. 导入导出 (Bundle)
    # =========================================================================

    def create_export_bundle(self, dynamic_rule_ids: List[str]):
        """生成规则包"""
        # 1. 过滤要导出的动态规则，如果 ids 为空列表，则不导出任何动态规则？
        # 或者我们定义：如果 ids 为 None，导出所有启用规则
        if dynamic_rule_ids is None:
            export_dynamic = [r for r in self.user_dynamic_rules if r.get('enabled', True)]
        else:
            export_dynamic = [r for r in self.user_dynamic_rules if r['rule_id'] in dynamic_rule_ids]
            
        # 2. 这里的策略是全量导出 UserModData 和 Groups，因为规则可能依赖这些环境
        return {
            "version": "1.0",
            "export_date": datetime.datetime.now().isoformat(),
            "user_rules": {
                "mod_rules": self.user_mod_rules,
                "dynamic_rules": export_dynamic
            },
            "environment": {
                "user_mod_data": ModDAO.get_all_user_data(),
                "groups": GroupDAO.get_all_groups_structured()
            }
        }

    def process_import_bundle(self, bundle: dict):
        """导入规则包（增量合并）"""
        rules = bundle.get("user_rules", {})
        
        # 1. 规则合并
        self.user_mod_rules.update(rules.get("mod_rules", {}))
        # 合并动态规则 (按 ID 去重)
        existing_ids = {r['rule_id'] for r in self.user_dynamic_rules}
        for r in rules.get("dynamic_rules", []):
            # 如果 ID 冲突，生成新 ID (导入副本)
            if r['rule_id'] in existing_ids:
                r['rule_id'] = f"{r['rule_id']}_import_{int(datetime.datetime.now().timestamp())}"
                r['name'] += " (Imported)"
            self.user_dynamic_rules.append(r)

        # 2. 环境数据合并 (UserModData & Groups)
        # 采用“静默合并”：
        # - UserModData: 仅当本地记录不存在或为空时补充。
        # - Groups: 创建新组，若重名则合并 Mod 成员。
        env = bundle.get("environment", {})
        
        # UserModData: 仅补充缺失字段，不覆盖已有非空字段
        for item in env.get("user_mod_data", []):
            pid = item.get('package_id')
            # 查现有数据
            # 这是一个优化的合并逻辑：先查数据库，对比后再更新
            # 但为了简单和性能，直接依赖 DAO 的 upsert 可能太粗暴
            # 这里建议：只更新那些本地没有设置过的属性
            # 比如本地已经把 Mod A 标红了，导入包里是蓝的，我们保留红的。
            # 这需要比较细致的逻辑，或者交给 DAO 处理。
            # 目前策略：直接由 DAO 层的 batch_upsert_user_data 处理，
            # 但我们需要构造一个仅包含“新信息”的 dict。
            
            # 构造更新字典，排除掉 Mod 基础属性，只保留用户定义的
            user_data_fields = {
                'alias_name': item.get('alias_name'),
                'notes': item.get('notes'),
                'tags': item.get('tags'),
                'sign_color': item.get('sign_color'),
                'user_mod_type': item.get('user_mod_type')
            }
            # 过滤掉 None 值，避免覆盖本地已有数据
            user_data_fields = {k: v for k, v in user_data_fields.items() if v is not None}
            if user_data_fields:
                ModDAO.update_user_data(pid, user_data_fields)

        # Groups: 合并同名组
        for g in env.get("groups", []):
            # 获取本地所有组名
            local_groups = GroupDAO.get_all_groups_structured()
            existing = next((lg for lg in local_groups if lg['name'] == g['name']), None)
            if existing:
                # 组名相同：合并 mod_ids 成员
                new_ids = list(set(existing['mod_ids'] + g.get('mod_ids', [])))
                GroupDAO.add_mods_to_group(existing['group_id'], new_ids)
            else:
                # 组名不同：新建组并添加成员
                new_g = GroupDAO.create_group(g['name'], g.get('color', '#ffffff'))
                GroupDAO.add_mods_to_group(new_g.group_id, g.get('mod_ids', []))

        self.save_user_rules()
        return True
    
    
    