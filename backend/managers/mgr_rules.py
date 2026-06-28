import os
import json
import re
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.utils.logger import logger
from backend.database.dao import ModDAO, GroupDAO
from backend.settings import RULES_DIR, USER_RULES_PATH, settings
from backend.utils.tools import current_ms
from backend._version import __version__

RULE_SOURCES = ["user", "native", "community", "dynamic"]

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
        self.community_rules_update_time: int = 0
        self.user_mod_rules: Dict[str, Any] = {}
        self.user_dynamic_rules: List[Dict[str, Any]] = []
        self.settings = {
            "community_mod_rules_enabled": True,    # 全局社区规则总开关
            "user_mod_rules_enabled": True,         # 全局用户单项规则总开关
            "dynamic_rules_enabled": True,          # 全局动态规则总开关
            "excluded_community_mods": [],          # 被禁用的社区 Mod ID 列表 (黑名单)
            "excluded_user_mods": [],               # 被禁用的用户 Mod ID 列表 (黑名单)
            # 规则优先级配置：索引越小，优先级越高 (默认: 用户 > 原生 > 社区 > 动态)
            "rule_source_priority": RULE_SOURCES 
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
                    self.community_rules_update_time = int(data.get("timestamp", data))*1000
                    
            # 加载用户规则
            user_file_path = Path(settings.config.user_rules_path)
            if user_file_path.exists():
                with open(user_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.user_mod_rules = data.get("mod_rules", {})
                    self.user_dynamic_rules = data.get("dynamic_rules", [])
                    # 加载设置
                    self.settings.update(data.get("settings", {}))
                    if set(self.settings["rule_source_priority"]) != set(RULE_SOURCES):
                        self.settings["rule_source_priority"] = RULE_SOURCES
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

    def change_rule_source_priority(self, rules_sources: List[str]):
        """改变规则来源的优先级"""
        if set(rules_sources) == set(self.settings["rule_source_priority"]):
            self.settings["rule_source_priority"] = rules_sources
            self.save_user_rules()
            return True
        return False
    
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
        """覆盖社区规则库"""
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
    
    def get_source_priority(self, source_type: str) -> int:
        """获取来源的优先级索引 (越小越优先)"""
        order = self.settings.get("rule_source_priority", ["user", "native", "community", "dynamic"])
        try:
            return order.index(source_type)
        except ValueError:
            return 999 # 未知来源优先级最低
        
    def get_effective_mod_rules(self, mod_id: str, mod_full_data: dict) -> Dict[str, Any]:
        """
        获取该 Mod 生效的最终规则集（经过优先级合并和去重）。
        优先级：Native > Community > User > Dynamic
        返回结构:
        {
            "dependencies": { "target_id": { "source": "native" } },
            "incompatible": { "target_id": { "source": "community", "detail": "..." } },
            "load_after":   { "target_id": { "source": "native" } },  # Native 覆盖了 Community
            "load_before":  { ... }
        }
        """
        mid_l = mod_id.lower()
        
        # 定义结果容器，使用字典方便按 target_id 去重
        # 结构: { "target_id": { "source": "...", "priority": int, "detail": ... } }
        # Priority: Native(4) > Community(3) > User(2) > Dynamic(1)
        rules_map = {
            "dependencies": {},
            "incompatible": {},
            "load_after": {},
            "load_before": {}
        }

        def _merge_rule(category, target, source_type, info=None):
            target = target.lower()
            current = rules_map[category].get(target)
            new_p_idx = self.get_source_priority(source_type)
            # 逻辑：如果当前没有规则，或者新规则的优先级索引更小（更靠前），则覆盖
            if not current or new_p_idx < current['priority_idx']:
                rules_map[category][target] = {
                    "source": source_type,
                    "priority_idx": new_p_idx,
                    "detail": info
                }

        # 1. Native (About.xml) - Priority 4
        # 依赖是特殊的，通常只有 Native 有，但为了统一结构也放这里
        for p in mod_full_data.get('dependencies_mods', []):
            rules_map["dependencies"][p['package_id'].lower()] = {"source": "native", "detail": None}
        for p in mod_full_data.get('incompatible_mods', []):
            _merge_rule("incompatible", p, "native")
        for p in mod_full_data.get('load_after_mods', []):
            _merge_rule("load_after", p, "native")
        for p in mod_full_data.get('load_before_mods', []):
            _merge_rule("load_before", p, "native")

        # 2. Community Rules - Priority 3
        if self.settings.get("community_mod_rules_enabled", True) and \
           mid_l not in self.settings.get("excluded_community_mods", []):
            comm = self.community_rules.get(mid_l, {})
            for t, info in comm.get("loadAfter", {}).items():
                _merge_rule("load_after", t, "community", info)
            for t, info in comm.get("loadBefore", {}).items():
                _merge_rule("load_before", t, "community", info)
            for t, info in comm.get("incompatibleWith", {}).items():
                _merge_rule("incompatible", t, "community", info)

        # 3. User Rules - Priority 2
        if self.settings.get("user_mod_rules_enabled", True) and \
           mid_l not in self.settings.get("excluded_user_mods", []):
            user = self.user_mod_rules.get(mid_l, {})
            rules = user.get("rules", user) # 兼容旧格式
            if isinstance(rules, dict):
                for t, info in rules.get("loadAfter", {}).items():
                    _merge_rule("load_after", t, "user", info)
                for t, info in rules.get("loadBefore", {}).items():
                    _merge_rule("load_before", t, "user", info)
                for t, info in rules.get("incompatibleWith", {}).items():
                    _merge_rule("incompatible", t, "user", info)

        # 4. Dynamic Rules - Priority 1
        if self.settings.get("dynamic_rules_enabled", True):
            matched = self.get_matching_dynamic_rules(mod_full_data)
            for rule in matched:
                act = rule.get("action", {})
                info = {"name": rule.get("name")}
                if act.get("type") == "load_after":
                    _merge_rule("load_after", act.get("value"), "dynamic", info)
                elif act.get("type") == "load_before":
                    _merge_rule("load_before", act.get("value"), "dynamic", info)

        # 转换为前端友好的 List 结构，并移除 priority 字段
        final_result = {}
        for cat, targets in rules_map.items():
            final_result[cat] = []
            for tid, data in targets.items():
                final_result[cat].append({
                    "target": tid,
                    "source": data["source"],
                    "detail": data.get("detail")
                })
        
        return final_result
    
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
            "version": __version__,
            "timestamp": current_ms(),
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
        """导入规则包"""
        from backend.database.models import db, UserModData, GroupData, GroupMod, ModAsset
        # 引入 chunked 用于分批处理大量数据
        from peewee import chunked

        rules = bundle.get("user_rules", {})
        env = bundle.get("environment", {})
        
        try:
            # 开启大事务，极大提升写入速度
            with db.atomic():
                # =================================================
                # 1. 规则合并 (内存操作)
                # =================================================
                self.user_mod_rules.update(rules.get("mod_rules", {}))
                
                # 动态规则去重合并
                existing_ids = {r['rule_id'] for r in self.user_dynamic_rules}
                for r in rules.get("dynamic_rules", []):
                    if r['rule_id'] in existing_ids:
                        # 冲突ID自动重命名
                        r['rule_id'] = f"{r['rule_id']}_imp_{int(datetime.datetime.now().timestamp())}"
                        r['name'] += " (Imported)"
                    self.user_dynamic_rules.append(r)

                # =================================================
                # 2. UserModData 批量导入 (备注、标签等)
                # =================================================
                user_data_list = env.get("user_mod_data", [])
                if user_data_list:
                    # 准备批量数据
                    batch_data = []
                    for item in user_data_list:
                        # 清洗数据，只保留有效字段
                        clean_item = {
                            'mod_id': item.get('mod_id'),
                            'alias_name': item.get('alias_name'),
                            'notes': item.get('notes'),
                            'tags': item.get('tags'),
                            'sign_color': item.get('sign_color'),
                            'user_mod_type': item.get('user_mod_type')
                        }
                        # 移除 None 值，防止覆盖本地已有数据（实现 Merge 逻辑）
                        # 但 batch_upsert 通常是全量覆盖或忽略，为了实现“仅更新非空值”比较复杂
                        # 这里采用策略：直接 Upsert。导入包通常代表“我想恢复成这样”。
                        if clean_item['mod_id']:
                            batch_data.append(clean_item)
                    
                    # 调用 DAO 的批量方法 (利用 on_conflict_replace 或 update)
                    # 注意：ModDAO.batch_upsert_user_data 需要支持部分字段更新
                    if batch_data:
                        ModDAO.batch_upsert_user_data(batch_data)

                # =================================================
                # 3. 分组数据导入 (直接 DB 操作)
                # =================================================
                imported_groups = env.get("groups", [])
                
                # 3.1 建立本地分组名称映射 {name: group_id}
                local_group_map = {g.name: g.group_id for g in GroupData.select()}
                
                group_mods_to_insert = [] # 待插入的关联关系
                
                for g in imported_groups:
                    g_name = g.get('name')
                    mod_ids = g.get('mod_ids', [])
                    
                    if not g_name: continue

                    # 确定 Group ID (存在则复用，不存在则创建)
                    if g_name in local_group_map:
                        target_gid = local_group_map[g_name]
                    else:
                        # 创建新分组
                        new_group = GroupDAO.create_group(g_name, g.get('color', '#ffffff'))
                        target_gid = new_group.group_id
                        local_group_map[g_name] = target_gid # 更新映射

                    # 收集该组的 Mod 关联
                    for mid in mod_ids:
                        group_mods_to_insert.append({
                            'group_id': target_gid,
                            'mod_id': mid
                        })

                # 3.2 批量插入分组关联
                if group_mods_to_insert:
                    # 【关键步骤】确保 UserModData 存在
                    # 因为 GroupMod 有外键指向 UserModData
                    # 如果导入包里的分组包含了一些 UserModData 里没有的 Mod (比如没备注也没标签的纯分组Mod)
                    # 直接插入 GroupMod 会报错。所以先插入“存根(Stub)”。
                    
                    stubs = [{'mod_id': item['mod_id']} for item in group_mods_to_insert]
                    # 批量插入存根，忽略已存在的
                    for batch in chunked(stubs, 500):
                        UserModData.insert_many(batch).on_conflict_ignore().execute()

                    # 3.3 插入 GroupMod 关联 (使用 Ignore 避免重复添加报错)
                    for batch in chunked(group_mods_to_insert, 500):
                        GroupMod.insert_many(batch).on_conflict_ignore().execute()

            # 事务结束，保存文件
            self.save_user_rules()
            logger.info("Import bundle processed successfully.")
            return True

        except Exception as e:
            logger.error(f"Failed to process import bundle: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 抛出异常让上层 API 捕获并返回错误信息给前端
            raise Exception(f"Import Error: {str(e)}")
    
    
    