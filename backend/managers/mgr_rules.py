import copy
import json
import re
import os
import datetime
import tempfile
import threading
from pathlib import Path
from typing import List, Dict, Any, Tuple
import uuid
from backend.managers.mgr_profile import ProfileContext
from backend.utils.logger import logger
from backend.database.dao import ModDAO, GroupDAO
from backend.settings import RULES_DIR, USER_RULES_PATH, settings
from backend.utils.tools import current_ms
from backend._version import __version__

RULE_SOURCES = ["user", "native", "community", "dynamic", "workshop"]

BUILTIN_RULES = {
    "rmm.companion": {
        "loadTop": {"value": True, "comment": "管理器伴生工具，必须极早期加载"},
        "loadAfter": {
            "brrainz.harmony": {"name": ["Harmony"], "comment": "必须在 Harmony 之后加载"}
        }
    },
}

SPECIAL_WEIGHTS = {
    'brrainz.harmony': 0,
    'ludeon.rimworld': 50,
    'ludeon.rimworld.royalty': 51,
    'ludeon.rimworld.ideology': 52,
    'ludeon.rimworld.biotech': 53,
    'ludeon.rimworld.anomaly': 54,
    'unlimitedhugs.hugslib': 110,
}

class RuleActionType:
    WEIGHT_SET = "weight_set"       # 强制设置权重 (0-1000)
    WEIGHT_SHIFT = "weight_shift"   # 权重偏移 (如 -50)
    LOAD_AFTER = "load_after"       # 必须在某ID后
    LOAD_BEFORE = "load_before"     # 必须在某ID前
    TOP = "top"                     # 置顶 (权重设为0)
    BOTTOM = "bottom"               # 置底 (权重设为10000)


DYNAMIC_WEIGHT_MIN = 1
DYNAMIC_WEIGHT_MAX = 9999
DYNAMIC_WEIGHT_SHIFT_MIN = -9999
DYNAMIC_WEIGHT_SHIFT_MAX = 9999
    
class RuleManager:
    def __init__(self, context: ProfileContext):
        # 内存中的规则缓存
        self.builtin_rules = BUILTIN_RULES # 挂载内置规则
        self.community_rules: Dict[str, Any] = {}
        self.community_rules_update_time: int = 0
        self.user_mod_rules: Dict[str, Any] = {}
        self.user_dynamic_rules: List[Dict[str, Any]] = []
        self.workshop_rules_cache: Dict[str, List[str]] = {} 
        self.context = context
        self.settings = self._build_default_settings()
        self._save_lock = threading.Lock()
        # 确保目录存在
        RULES_DIR.mkdir(parents=True, exist_ok=True)
        self.load_all()

    def _build_default_settings(self) -> dict[str, Any]:
        """构造规则系统默认设置，便于重载时回到干净基线。"""
        return {
            "community_mod_rules_enabled": True,    # 全局社区规则总开关
            "user_mod_rules_enabled": True,         # 全局用户单项规则总开关
            "dynamic_rules_enabled": True,          # 全局动态规则总开关
            "workshop_mod_rules_enabled": True,         # 工坊外置规则总开关
            "workshop_rules_as_dependency": False,  # True: 作为强依赖(触发自动补全) | False: 作为普通前置依赖
            "excluded_community_mods": [],          # 被禁用的社区 Mod ID 列表 (黑名单)
            "excluded_user_mods": [],               # 被禁用的用户 Mod ID 列表 (黑名单)
            "excluded_workshop_mods": [],           # 被禁用的工坊 Mod ID 列表 (黑名单)
            # 规则优先级配置：索引越小，优先级越高 (默认: 用户 > 原生 > 社区 > 动态)
            "rule_source_priority": RULE_SOURCES 
        }

    def _get_user_rules_path(self) -> Path:
        """统一解析用户规则文件路径，避免读写目标漂移。"""
        configured_path = str(getattr(settings.config, "user_rules_path", "") or "").strip()
        return Path(configured_path) if configured_path else USER_RULES_PATH

    def _parse_community_rules_timestamp(self, payload: dict[str, Any]) -> int:
        """
        兼容社区规则库的多种时间戳格式。
        - 缺失时间戳时返回 0，不阻断用户规则加载。
        - 秒级时间戳自动转毫秒；毫秒级原样保留。
        """
        raw_timestamp = payload.get("timestamp")
        if raw_timestamp in (None, ""):
            return 0
        try:
            parsed = int(raw_timestamp)
        except (TypeError, ValueError):
            logger.warning(f"Community rules timestamp is invalid: {raw_timestamp!r}")
            return 0
        return parsed if parsed >= 10**11 else parsed * 1000

    def _load_community_rules(self):
        """独立加载社区规则，避免其异常误伤用户规则。"""
        self.community_rules = {}
        self.community_rules_update_time = 0
        community_file_path = Path(settings.config.community_rules_path)
        if not community_file_path.exists(): return

        with open(community_file_path, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Community rules root is not an object")

        # 兼容不同格式：既支持 {\"rules\": {...}}，也支持直接以规则字典作为根对象。
        rules_payload = data.get("rules")
        self.community_rules = rules_payload if isinstance(rules_payload, dict) else data
        self.community_rules_update_time = self._parse_community_rules_timestamp(data)

    def _load_user_rules(self):
        """独立加载用户规则，路径切换时先清空旧状态再按新文件重建。"""
        self.user_mod_rules = {}
        self.user_dynamic_rules = []
        self.settings = self._build_default_settings()

        user_file_path = self._get_user_rules_path()
        if not user_file_path.exists(): return

        with open(user_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("User rules root is not an object")

        mod_rules = data.get("mod_rules", {})
        if isinstance(mod_rules, dict):
            self.user_mod_rules = mod_rules
        else:
            logger.warning("加载用户规则时发现 mod_rules 格式无效，已重置为空。")
            self.user_mod_rules = {}

        sanitized_dynamic_rules, sanitize_warnings, _ = self._sanitize_dynamic_rules(
            data.get("dynamic_rules", []),
            origin="加载动态规则"
        )
        self.user_dynamic_rules = sanitized_dynamic_rules
        for warning in sanitize_warnings:
            logger.warning(warning)

        loaded_settings = data.get("settings", {})
        if isinstance(loaded_settings, dict):
            self.settings.update(loaded_settings)
        else:
            logger.warning("加载用户规则时发现 settings 格式无效，已忽略。")

        if set(self.settings.get("rule_source_priority", [])) != set(RULE_SOURCES):
            self.settings["rule_source_priority"] = RULE_SOURCES

    def _write_json_atomic(self, target_path: Path, payload: dict[str, Any], purpose: str):
        """
        以“临时文件 + fsync + replace”方式原子写入 JSON。
        这样可避免程序中断时把目标文件写成半截内容。
        """
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd = None
        temp_path = None
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{target_path.stem}.",
                suffix=".tmp",
                dir=str(target_path.parent),
            )
            temp_path = Path(temp_name)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                fd = None
                json.dump(payload, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target_path)
        except Exception as e:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"{purpose}失败: {e}") from e

    def load_all(self):
        """核心：从磁盘加载所有规则数据"""
        try:
            self._load_community_rules()
        except Exception as e:
            logger.error(f"Failed to load community rules: {e}", exc_info=True)

        try:
            self._load_user_rules()
        except Exception as e:
            logger.error(f"Failed to load user rules: {e}", exc_info=True)
            # 用户规则损坏时回到空白基线，避免残留旧内存数据继续污染 UI。
            self.user_mod_rules = {}
            self.user_dynamic_rules = []
            self.settings = self._build_default_settings()

        try:
            self.build_workshop_rules()
        except Exception as e:
            logger.error(f"Failed to rebuild workshop rules cache: {e}", exc_info=True)

    def save_user_rules(self):
        """持久化用户规则"""
        try:
            with self._save_lock:
                sanitized_dynamic_rules, sanitize_warnings, _ = self._sanitize_dynamic_rules(
                    self.user_dynamic_rules,
                    origin="保存动态规则"
                )
                self.user_dynamic_rules = sanitized_dynamic_rules
                for warning in sanitize_warnings:
                    logger.warning(warning)
                data = {
                    "meta": {
                        # 仅记录文件元信息，便于排查“哪份规则文件更新得更晚”。
                        "schema_version": 1,
                        "updated_at": current_ms(),
                        "written_by": __version__,
                    },
                    "settings": self.settings, # 保存设置
                    "mod_rules": self.user_mod_rules,
                    "dynamic_rules": self.user_dynamic_rules
                }
                self._write_json_atomic(self._get_user_rules_path(), data, "保存用户规则")
            return True
        except Exception as e:
            logger.error(f"Failed to save user rules: {e}", exc_info=True)
            raise
    
    def build_workshop_rules(self):
        """
        精准构建工坊依赖缓存：仅针对本地已安装/存在的 Mod 构建规则。
        """
        from backend.database.models_ext import WorkshopManifest, ext_db
        from backend.database.models import ModAsset
        if ext_db.database is None: return
        try:
            if not WorkshopManifest.table_exists(): return
            # 1. 【核心过滤】从主数据库获取所有已安装/存在的 package_id (去重且转小写)
            # 只有这些 Mod 才需要我们去查询它们的依赖关系
            installed_pids = [
                m.package_id.lower() 
                for m in ModAsset.select(ModAsset.package_id).distinct() 
                if m.package_id
            ]
            if not installed_pids:
                self.workshop_rules_cache = {}
                return
            # 2. 从外置库中查询这些 Package ID 对应的元数据 (获取它们的原始依赖列表)
            # WHERE package_id IN (...)
            active_metas = list(WorkshopManifest.select(
                WorkshopManifest.package_id,
                WorkshopManifest.dependencies_mods
            ).where(WorkshopManifest.package_id << installed_pids).dicts())
            if not active_metas:
                self.workshop_rules_cache = {}
                return
            # 3. 收集这些依赖中涉及到的所有目标 Workshop ID
            # 我们需要把这些 Workshop ID 转换回 Package ID，排序引擎才能识别
            all_target_wids = set()
            for row in active_metas:
                if row['dependencies_mods']:
                    # 依赖格式: {"2891845502": "Name"}
                    all_target_wids.update(row['dependencies_mods'].keys())
            if not all_target_wids:
                self.workshop_rules_cache = {}
                return
            # 4. 仅查询这部分目标 Workshop ID 对应的 Package ID
            # 这样避免了全量加载 wid_to_pid 映射
            wid_to_pid_map = {
                str(m.workshop_id): m
                for m in WorkshopManifest.select(WorkshopManifest.workshop_id, WorkshopManifest.name, WorkshopManifest.package_id)
                                    .where(WorkshopManifest.workshop_id << list(all_target_wids))
                if m.package_id
            }
            # 5. 组装最终缓存
            new_cache = {}
            for row in active_metas:
                source_pid = row['package_id'].lower()
                raw_deps = row['dependencies_mods'] # dict
                if not raw_deps: continue
                resolved_target_pids = []
                for target_wid in raw_deps.keys():
                    target_mod = wid_to_pid_map.get(str(target_wid))
                    if target_mod:
                        resolved_target_pids.append((target_mod.package_id.lower(), target_mod.name))
                if resolved_target_pids:
                    new_cache[source_pid] = resolved_target_pids
            self.workshop_rules_cache = new_cache
            logger.info(f"Workshop rules cache built. Active: {len(new_cache)} mods.")
        except Exception as e:
            logger.error(f"Failed to build workshop rules cache: {e}", exc_info=True)
    
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
    
    def toggle_workshop_mod_exclusion(self, package_id: str, exclude: bool):
        """将某个 Mod 加入/移出工坊规则黑名单"""
        pid = package_id.lower().strip()
        excluded_list = self.settings["excluded_workshop_mods"]
        if exclude and pid not in excluded_list:
            excluded_list.append(pid)
        elif not exclude and pid in excluded_list:
            excluded_list.remove(pid)
        self.save_user_rules()
        return True
    
    def _is_version_compatible(self, requirements: list) -> bool:
        """
        检查规则是否适用于当前游戏版本
        requirements: ['all'] 或 ['1.5', '1.6']
        """
        if requirements is None: return False
        # 如果包含 'all'，或者列表为空（默认兼容），直接通过
        if isinstance(requirements, list) and ('all' in requirements or not requirements): return True
        
        # 获取当前游戏版本 (例如 "1.5.4100" -> "1.5")
        # 注意：settings.config.game_version 可能为空，需兜底
        current_ver = self.context.game_version
        if not current_ver: return True # 无法确定版本时，默认放行，或者可以选择严格模式 return False
            
        short_ver = current_ver[:3] # 取前三位 "1.5"
        # logger.debug(f"Current game version: {current_ver}, short version: {short_ver}, requirements: {requirements}")
        return short_ver in requirements

    def _clamp_int(self, value: Any, default: int, min_value: int, max_value: int) -> Tuple[int, bool, Any]:
        """将输入值规整为 int，并按区间夹紧。"""
        raw_value = value
        parse_failed = False
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
            parse_failed = True
        clamped = max(min_value, min(max_value, parsed))
        changed = parse_failed or clamped != parsed
        return clamped, changed, raw_value

    def _clamp_dynamic_weight(self, value: Any, default: int = 500) -> Tuple[int, bool, Any]:
        return self._clamp_int(value, default, DYNAMIC_WEIGHT_MIN, DYNAMIC_WEIGHT_MAX)

    def _clamp_dynamic_shift(self, value: Any, default: int = 0) -> Tuple[int, bool, Any]:
        return self._clamp_int(value, default, DYNAMIC_WEIGHT_SHIFT_MIN, DYNAMIC_WEIGHT_SHIFT_MAX)

    def _clamp_dynamic_effective_weight(self, value: int) -> int:
        return max(DYNAMIC_WEIGHT_MIN, min(DYNAMIC_WEIGHT_MAX, int(value)))

    def _sanitize_dynamic_rule(self, rule_obj: dict, origin: str = "动态规则") -> Tuple[dict, List[str], bool]:
        """清洗动态规则中的数值动作，避免越界权重污染排序。"""
        clean_rule = copy.deepcopy(rule_obj) if isinstance(rule_obj, dict) else {}
        warnings = []
        changed = not isinstance(rule_obj, dict)

        if not clean_rule:
            warnings.append(f"{origin} 格式无效，已重置为空规则。")
            clean_rule = {"rule_id": f"dynamic_{uuid.uuid4().hex[:8]}", "enabled": True}
            return clean_rule, warnings, True

        if not clean_rule.get("rule_id"):
            clean_rule["rule_id"] = f"dynamic_{uuid.uuid4().hex[:8]}"
            warnings.append(f"{origin} 缺少 rule_id，已自动补全。")
            changed = True

        try:
            clean_priority = int(clean_rule.get("priority", 100))
        except (TypeError, ValueError):
            clean_priority = 100
        if clean_rule.get("priority") != clean_priority:
            clean_rule["priority"] = clean_priority
            changed = True

        logic = str(clean_rule.get("logic", "AND") or "AND").upper()
        if logic not in {"AND", "OR"}:
            logic = "AND"
            changed = True
        clean_rule["logic"] = logic

        filters = clean_rule.get("filters")
        if isinstance(filters, list):
            for idx, filter_item in enumerate(filters, start=1):
                if not isinstance(filter_item, dict):
                    continue
                field = str(filter_item.get("field") or "").strip()
                if field == "user_mod_type":
                    filter_item["field"] = "mod_type"
                    changed = True

        action = clean_rule.get("action")
        if not isinstance(action, dict): return clean_rule, warnings, changed

        act_type = action.get("type")
        if act_type == RuleActionType.WEIGHT_SET:
            clamped, value_changed, raw_value = self._clamp_dynamic_weight(action.get("value", 500), default=500)
            action["value"] = clamped
            if value_changed:
                warnings.append(f"{origin} 的强制权重 {raw_value!r} 无效或超出允许范围，已限制为 {clamped}。")
                changed = True
        elif act_type == RuleActionType.WEIGHT_SHIFT:
            clamped, value_changed, raw_value = self._clamp_dynamic_shift(action.get("value", 0), default=0)
            action["value"] = clamped
            if value_changed:
                warnings.append(f"{origin} 的权重偏移 {raw_value!r} 无效或超出允许范围，已限制为 {clamped}。")
                changed = True

        return clean_rule, warnings, changed

    def _sanitize_dynamic_rules(self, rules: Any, origin: str = "动态规则") -> Tuple[List[dict], List[str], bool]:
        """批量清洗动态规则列表。"""
        if not isinstance(rules, list): return [], [f"{origin} 列表格式无效，已重置为空。"], True

        sanitized_rules = []
        warnings = []
        changed = False
        for idx, rule in enumerate(rules, start=1):
            clean_rule, rule_warnings, rule_changed = self._sanitize_dynamic_rule(rule, f"{origin} #{idx}")
            sanitized_rules.append(clean_rule)
            warnings.extend(rule_warnings)
            changed = changed or rule_changed
        return sanitized_rules, warnings, changed

    def _resolve_condition_field(self, mod_data: dict, field: str):
        """解析筛选字段，支持别名与点分路径。"""
        field_aliases = {
            "mod_type": ["user_mod_type", "mod_type"],
            "user_mod_type": ["user_mod_type", "mod_type"],
            # 名称只匹配原始 name；别名则允许“别名 / 显示名 / 原名”三者任一命中。
            "name": ["name"],
            "alias_name": ["alias_name", "display_name", "name"],
        }

        def _resolve_path(data, path: str):
            current = data
            for part in path.split('.'):
                if isinstance(current, dict): current = current.get(part)
                else: return None
            return current

        candidate_fields = field_aliases.get(field, [field])
        # alias_name 的语义是“用户眼里看到的名字”，因此要把多个候选字段聚合后一起参与匹配。
        multi_value_fields = {"alias_name"}
        collected_values = []
        for candidate in candidate_fields:
            value = _resolve_path(mod_data, candidate)
            if value is not None:
                if field in multi_value_fields:
                    if isinstance(value, list):
                        collected_values.extend(value)
                    else:
                        collected_values.append(value)
                else:
                    return value
        if field in multi_value_fields and collected_values:
            unique_values = []
            seen = set()
            for item in collected_values:
                key = str(item).strip().lower()
                if not key or key in seen: continue
                seen.add(key)
                unique_values.append(item)
            return unique_values or None
        return None
    
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

    def set_language_pack_owner_override(
        self,
        package_id: str,
        owner_ids: list[str],
        replace: bool = False,
    ):
        """设置语言包归属手动覆盖。"""
        pid = package_id.lower().strip()
        if pid not in self.user_mod_rules:
            self.user_mod_rules[pid] = {}

        rule = self.user_mod_rules[pid]
        normalized_owner_ids = []
        seen = set()
        for owner_id in owner_ids or []:
            normalized_id = str(owner_id or "").strip().lower()
            if not normalized_id or normalized_id in seen: continue
            seen.add(normalized_id)
            normalized_owner_ids.append(normalized_id)

        replace_enabled = bool(replace and normalized_owner_ids)

        if normalized_owner_ids:
            rule["languagePackOwners"] = {
                "owners": normalized_owner_ids,
                "replace": replace_enabled,
            }
        else:
            rule.pop("languagePackOwners", None)

        if not rule:
            del self.user_mod_rules[pid]

        self.save_user_rules()
        return True

    def set_user_mod_absolute_position(self, package_id: str, position: str, comment: str = ""):
        """
        设置某个 Mod 的绝对位置属性 (top / bottom / none)
        """
        pid = package_id.lower().strip()
        if pid not in self.user_mod_rules:
            self.user_mod_rules[pid] = {}
            
        rule = self.user_mod_rules[pid]
        
        # 先清理旧状态
        rule.pop("loadTop", None)
        rule.pop("loadBottom", None)
        
        # 赋予新状态
        if position == "top":
            rule["loadTop"] = {"value": True, "comment": comment}
        elif position == "bottom":
            rule["loadBottom"] = {"value": True, "comment": comment}
            
        # 如果这个 Mod 没有任何规则了，清理掉它
        if not rule:
            del self.user_mod_rules[pid]
            
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
        clean_rule, sanitize_warnings, _ = self._sanitize_dynamic_rule(rule_obj, origin="保存动态规则")
        for warning in sanitize_warnings:
            logger.warning(warning)

        rid = clean_rule.get('rule_id')
        if not rid: return False
        # 查找是否存在
        idx = next((i for i, r in enumerate(self.user_dynamic_rules) if r['rule_id'] == rid), -1)
        if idx > -1:
            self.user_dynamic_rules[idx] = clean_rule
        else:
            self.user_dynamic_rules.append(clean_rule)
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
            self._write_json_atomic(Path(settings.config.community_rules_path), data, "覆盖社区规则库")
            self.load_all()
            return True
        except Exception as e:
            logger.error(f"Failed to update community rules: {e}")
            raise e

    # =========================================================================
    # 2. 匹配与查询 (Engine)
    # =========================================================================

    
    def calculate_mod_base_weight(self, mod_data: dict) -> int:
        """
        根据 Mod 数据计算单一 Mod 的基础权重
        """
        pkg_id = mod_data.get('package_id', '').lower().strip()
        # 1. 检查特殊硬编码 ID
        if pkg_id in SPECIAL_WEIGHTS: return SPECIAL_WEIGHTS[pkg_id]
        # 2. 根据作者判定 (官方作者)
        authors = mod_data.get('author', [])
        if 'Ludeon Studios' in authors: return 60
        # 3. 根据 Mod 类型判定 (来自 analyzer.py 的分析结果)
        mod_type = str(mod_data.get('user_mod_type') or mod_data.get('mod_type', 'Unknown')).strip()
        if mod_type == 'LanguagePack': return 900  # 汉化包置底
        if mod_type == 'Texture': return 850  # 纹理包置后
        if mod_type == 'Audio': return 860  # 音频包置后
        # 4. 根据 ID 关键字模糊判定
        if '.lib' in pkg_id or 'library' in pkg_id: return 150
        if 'framework' in pkg_id: return 160
        # 5. 默认权重 (普通 Mod)
        return 500

    
    def _match_mod_condition(self, mod_data: dict, filter_item: dict) -> bool:
        """
        判断一个 Mod 是否满足某项过滤条件
        mod_data: 包含基础 Mod 信息和 UserModData 的合并字典
        """
        field = filter_item.get("field")
        op = filter_item.get("operator")
        target = str(filter_item.get("value", "")).lower()
        # 获取实际值，支持点分语法 (例如 metadata.author)
        actual = self._resolve_condition_field(mod_data, str(field or "").strip())
        if actual is None: return False
        # 统一转为字符串列表进行匹配
        if isinstance(actual, list):
            actual_strs = [str(i).lower() for i in actual]
        else:
            actual_strs = [str(actual).lower()]

        try:
            if op == "equals": return any(target == s for s in actual_strs)
            if op == "not_equals": return all(target != s for s in actual_strs)
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
        # 动态规则的 priority 是用户显式编辑的执行顺序：
        # 数值越小越先尝试，这样前端展示顺序和后端真实生效顺序一致。
        ordered_rules = sorted(
            self.user_dynamic_rules,
            key=lambda r: (
                int(r.get("priority", 100)) if str(r.get("priority", "100")).lstrip("-").isdigit() else 100,
                str(r.get("rule_id", "")),
            )
        )
        for rule in ordered_rules:
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
        if source_type == "builtin":  return -1  # 内置规则 -1 永远比列表中的索引 (0, 1, 2...) 小，绝对优先！
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
            "load_before":  { ... },
            "weight_override": {"type": "top"|"bottom", "source": "user", "detail": "..."}
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
            "load_before": {},
            "weight_override": None # 用于记录绝对位置覆盖（置顶/置底）
        }
        
        # 预先计算基础权重与偏移量
        base_weight = self.calculate_mod_base_weight(mod_full_data)
        weight_shift = 0
        dynamic_weight_touched = False
        
        # 辅助函数：处理置顶/置底优先级覆盖
        def _apply_weight_override(w_type: str, source_type: str, detail: Any = None):
            new_p_idx = self.get_source_priority(source_type)
            current = rules_map["weight_override"]
            
            # 如果没有，或者新来源优先级更高(索引更小)，则覆盖
            if not current or new_p_idx < current['priority_idx']:
                rules_map["weight_override"] = {
                    "type": w_type,
                    "source": {"type": source_type, "detail": detail},
                    "priority_idx": new_p_idx
                }
        def _merge_rule(category: str, target_id: str, source_type: str, source_name: str, 
                        is_force: bool = False, alternatives: list = [], detail: Any = None):
            target_id = target_id.lower()
            if not target_id: return
            
            new_p_idx = self.get_source_priority(source_type)
            current = rules_map[category].get(target_id)
            
            # 如果当前没有规则，或者新规则的优先级更高(索引更小)，则覆盖
            should_override = False
            if not current:
                should_override = True  # 规则不存在，直接写入
            elif is_force and not current['is_force']:
                should_override = True  # 新规则是强制的，旧的不是，直接降维覆盖（无视来源优先级）
            elif is_force == current['is_force'] and new_p_idx < current['priority_idx']:
                should_override = True  # 二者同为强制(或同为非强制)，遵循来源优先级（如：用户的强制 覆盖 原版的强制）
                
            if should_override:
                rules_map[category][target_id] = {
                    "target_id": target_id,
                    "type": category,
                    "version_requirement": ["all"], # 输出时已是清洗过的，统一标为 all 即可
                    "alternatives": alternatives or [],
                    "is_force": is_force,
                    "source": {
                        "type": source_type,
                        "name": source_name,
                        "detail": detail
                    },
                    "priority_idx": new_p_idx # 内部计算字段，最终剔除
                }

        # 1. Native (About.xml) - 优先级: native
        # 不受黑名单机制影响，严格执行游戏版本过滤
        native_mapping = {
            'dependencies_mods': ('dependencies', '原生依赖'),
            'load_after_mods': ('load_after', '原生前置'),
            'load_before_mods': ('load_before', '原生后置'),
            'incompatible_mods': ('incompatible', '原生冲突')
        }
        for field, (cat, name) in native_mapping.items():
            for rule in mod_full_data.get(field, []):
                # 兼容部分未完全转换的旧格式
                if isinstance(rule, str):
                    rule = {"package_id": rule, "version_requirement": ['all'], "alternatives": [], "is_force": False}
                
                # 核心：版本过滤 (过滤掉不属于当前游戏版本的规则)
                if self._is_version_compatible(rule.get('version_requirement')): # type: ignore
                    _merge_rule(
                        category=cat,
                        target_id=rule.get('package_id', ''),
                        source_type="native",
                        source_name=name,
                        is_force=rule.get('is_force', False),
                        alternatives=rule.get('alternatives', []),
                        detail={"versions": rule.get('version_requirement')}
                    )
        
        # 2. Community Rules
        # 受全局开关和黑名单控制
        if self.settings.get("community_mod_rules_enabled", True) and \
           mid_l not in self.settings.get("excluded_community_mods", []):
            comm = self.community_rules.get(mid_l, {})
            for t, info in comm.get("loadAfter", {}).items():
                _merge_rule("load_after", t, "community", "社区前置", detail=info)
            for t, info in comm.get("loadBefore", {}).items():
                _merge_rule("load_before", t, "community", "社区后置", detail=info)
            for t, info in comm.get("incompatibleWith", {}).items():
                _merge_rule("incompatible", t, "community", "社区冲突", detail=info)
            # 解析 loadTop 和 loadBottom
            # 格式例如: "loadBottom": {"value": True, "comment": "必须置底"}
            isTop = comm.get("loadTop", {}).get("value") 
            isBottom = comm.get("loadBottom", {}).get("value") 
            if isTop is not None and (isTop is True or isTop.lower() == "true"):
                _apply_weight_override("top", "community", comm.get("loadTop", {}).get("comment"))
            elif isBottom is not None and (isBottom is True or isBottom.lower() == "true"):
                _apply_weight_override("bottom", "community", comm.get("loadBottom", {}).get("comment"))

        # 3. User Rules - Priority 2
        # 受全局开关和黑名单控制
        if self.settings.get("user_mod_rules_enabled", True) and \
           mid_l not in self.settings.get("excluded_user_mods", []):
            user = self.user_mod_rules.get(mid_l, {})
            rules = user.get("rules", user) # 兼容旧格式
            if isinstance(rules, dict):
                for t, info in rules.get("loadAfter", {}).items():
                    _merge_rule("load_after", t, "user", "用户前置", detail=info)
                for t, info in rules.get("loadBefore", {}).items():
                    _merge_rule("load_before", t, "user", "用户后置", detail=info)
                for t, info in rules.get("incompatibleWith", {}).items():
                    _merge_rule("incompatible", t, "user", "用户冲突", detail=info)
                # 解析 loadTop 和 loadBottom
                # 格式例如: "loadBottom": {"value": True, "comment": "必须置底"}
                isTop = user.get("loadTop", {}).get("value") 
                isBottom = user.get("loadBottom", {}).get("value") 
                if isTop is not None and (isTop is True or isTop.lower() == "true"):
                    _apply_weight_override("top", "user", user.get("loadTop", {}).get("comment"))
                elif isBottom is not None and (isBottom is True or isBottom.lower() == "true"):
                    _apply_weight_override("bottom", "user", user.get("loadBottom", {}).get("comment"))

        # 4. Dynamic Rules - Priority 1
        # 仅提取图约束 (load_after / load_before)，其余权重操作交由排序器处理
        if self.settings.get("dynamic_rules_enabled", True):
            matched = self.get_matching_dynamic_rules(mod_full_data)
            for rule in matched:
                act = rule.get("action", {})
                rule_name = rule.get("name", "动态规则")
                act_type = act.get("type")
                if act_type == "load_after":
                    _merge_rule("load_after", act.get("value"), "dynamic", rule_name)
                elif act_type == "load_before":
                    _merge_rule("load_before", act.get("value"), "dynamic", rule_name)
                # [新增] 集中处理动态规则的权重干预，并利用已有的 _apply_weight_override 参与优先级竞争
                elif act_type == "weight_shift":
                    shift_value, _, _ = self._clamp_dynamic_shift(act.get("value", 0), default=0)
                    weight_shift += shift_value
                    dynamic_weight_touched = True
                elif act_type == "weight_set":
                    set_value, _, _ = self._clamp_dynamic_weight(act.get("value", base_weight), default=base_weight)
                    base_weight = set_value
                    dynamic_weight_touched = True
                elif act_type == "top":
                    _apply_weight_override("top", "dynamic", rule_name)
                elif act_type == "bottom":
                    _apply_weight_override("bottom", "dynamic", rule_name)
                    
        
        # 5. Workshop External Rules (工坊外置依赖规则)
        if self.settings.get("workshop_mod_rules_enabled", True) and \
            mid_l not in self.settings.get("excluded_workshop_mods", []):
            deps = self.workshop_rules_cache.get(mid_l, [])
            is_strict = self.settings.get("workshop_rules_as_dependency", False)
            # 根据开关决定作为 强依赖(dependencies) 还是 弱前置(load_after)
            cat = "dependencies" if is_strict else "load_after"
            source_name = "工坊依赖数据" if is_strict else "工坊前置数据"
            for dep_pid, name in deps:
                _merge_rule(
                    category=cat,
                    target_id=dep_pid,
                    source_type="workshop",
                    source_name=source_name,
                )
        
        # 6. Builtin Rules (内置规则)
        builtin = self.builtin_rules.get(mid_l)
        if builtin:
            for t, info in builtin.get("loadAfter", {}).items():
                _merge_rule("load_after", t, "builtin", "系统内置规则", detail=info)
            for t, info in builtin.get("loadBefore", {}).items():
                _merge_rule("load_before", t, "builtin", "系统内置规则", detail=info)
            for t, info in builtin.get("incompatibleWith", {}).items():
                _merge_rule("incompatible", t, "builtin", "系统内置规则", detail=info)
            
            isTop = builtin.get("loadTop", {}).get("value") 
            isBottom = builtin.get("loadBottom", {}).get("value") 
            if isTop:
                _apply_weight_override("top", "builtin", builtin.get("loadTop", {}).get("comment"))
            elif isBottom:
                _apply_weight_override("bottom", "builtin", builtin.get("loadBottom", {}).get("comment"))

        # 5. 格式化输出
        final_result = {
            "dependencies": [],
            "load_after": [],
            "load_before": [],
            "incompatible": [],
            "weight_info": {}
        }
        for cat in ["dependencies", "load_after", "load_before", "incompatible"]:
            for tid, data in rules_map[cat].items():
                del data['priority_idx'] # 剔除内部计算字段
                final_result[cat].append(data)
        
        # 附加绝对位置规则 (如果有)
        # if rules_map["weight_override"]:
        #     del rules_map["weight_override"]['priority_idx']
        #     final_result["weight_override"] = rules_map["weight_override"]
        # else:
        #     final_result["weight_override"] = []
        
        
        # [修改] 封装统一的 weight_info 供 Sorter 无脑读取
        abs_override = rules_map["weight_override"]
        # 统一计算 final_weight
        final_weight = base_weight + weight_shift
        abs_type = abs_override["type"] if abs_override else None
        if abs_type == "top":
            final_weight = 0
        elif abs_type == "bottom":
            final_weight = 10000
        elif dynamic_weight_touched:
            final_weight = self._clamp_dynamic_effective_weight(final_weight)
        
        final_result["weight_info"] = {
            "base_weight": base_weight,
            "weight_shift": weight_shift,
            "final_weight": final_weight,
            "absolute_type": abs_type,
            "absolute_source": abs_override["source"]["type"] if abs_override else None
        }
        
        return final_result

    def get_workshop_rules(self, package_id: str = '') -> Dict[str, Any]:
        """
        获取工坊依赖规则的标准格式。
        如果提供 package_id，返回该 Mod 的规则；否则返回所有已构建的工坊规则。
        返回格式等同于 self.community_rules。
        """
        # 内部转换逻辑：将 [id1, id2] 转换为 {"loadAfter": {"id1": {...}, "id2": {...}}}
        is_strict = self.settings.get("workshop_rules_as_dependency", False)
        def _transform(mod: List[str]):
            rules = {
                pid: {"comment": "来自工坊元数据", "name": name} 
                for pid, name in mod
            }
            return {
                "dependencies": rules if is_strict else {},
                "loadAfter": rules if not is_strict else {},
                "loadBefore": {},
                "incompatibleWith": {}
            }
        # 情况 1：获取单个 Mod 的规则
        if package_id:
            pid_l = package_id.lower().strip()
            mod = self.workshop_rules_cache.get(pid_l)
            return _transform(mod) if mod else {}
        # 情况 2：获取全量已生成的工坊规则
        all_rules = {}
        for pid, mod in self.workshop_rules_cache.items():
            all_rules[pid] = _transform(mod)
            
        return all_rules
    
    # =========================================================================
    # 3. 导入导出 (Bundle)
    # =========================================================================

    def create_export_bundle(self, dynamic_rule_ids: List[str]):
        """生成规则包"""
        from backend.database.models import ModInterlock
        # 1. 过滤要导出的动态规则，如果 ids 为空列表，则不导出任何动态规则？
        # 或者定义：如果 ids 为 None，导出所有启用规则
        if dynamic_rule_ids is None:
            export_dynamic = [r for r in self.user_dynamic_rules if r.get('enabled', True)]
        else:
            export_dynamic = [r for r in self.user_dynamic_rules if r['rule_id'] in dynamic_rule_ids]
        # 获取所有的联锁组
        all_interlocks = list(ModInterlock.select().dicts())
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
                "groups": GroupDAO.get_all_groups_structured(),
                "interlocks": all_interlocks
            }
        }

    def process_import_bundle(self, bundle: dict):
        """导入规则包"""
        from backend.database.models import db, UserModData, GroupData, GroupMod, ModAsset, ModInterlock
        # 引入 chunked 用于分批处理大量数据
        from peewee import chunked

        rules = bundle.get("user_rules", {})
        env = bundle.get("environment", {})
        import_warnings = []
        
        try:
            # 开启大事务，极大提升写入速度
            with db.atomic():
                # =================================================
                # 1. 规则合并 (内存操作)
                # =================================================
                self.user_mod_rules.update(rules.get("mod_rules", {}))
                # 动态规则去重合并
                existing_ids = {r['rule_id'] for r in self.user_dynamic_rules}
                imported_dynamic_rules, sanitize_warnings, _ = self._sanitize_dynamic_rules(
                    rules.get("dynamic_rules", []),
                    origin="导入动态规则"
                )
                import_warnings.extend(sanitize_warnings)
                for r in imported_dynamic_rules:
                    if r['rule_id'] in existing_ids:
                        # 冲突ID自动重命名
                        old_rule_id = r['rule_id']
                        r['rule_id'] = f"{r['rule_id']}_imp_{uuid.uuid4().hex[:8]}"
                        r['name'] = f"{r.get('name', old_rule_id)} (Imported)"
                        import_warnings.append(
                            f"导入动态规则 ID {old_rule_id} 与现有规则重复，已自动重命名为 {r['rule_id']}。"
                        )
                    self.user_dynamic_rules.append(r)
                    existing_ids.add(r['rule_id'])
                
                # =================================================
                # 2. UserModData 批量导入 (备注、标签等)
                # =================================================
                user_data_list = env.get("user_mod_data", [])
                if user_data_list:
                    # 准备批量数据
                    batch_data = []
                    valid_field_names = set(UserModData._meta.fields.keys()) # type: ignore
                    # ==== 旧链表兼容池 ====
                    legacy_locks = {} # { mod_id: { prev: xxx, next: yyy } }
                    for item in user_data_list:
                        # 清洗数据，只保留有效字段
                        clean_item={}
                        for k in list(item.keys()):
                            if k in valid_field_names:
                                clean_item[k] = item[k]
                        # 拦截旧版链表数据
                        pid = item.get('mod_id', '').lower()
                        if pid and ('lock_previous_mod' in item or 'lock_next_mod' in item):
                            prev_id = item.get('lock_previous_mod')
                            next_id = item.get('lock_next_mod')
                            if prev_id or next_id:
                                legacy_locks[pid] = {
                                    'prev': prev_id.lower() if prev_id else None,
                                    'next': next_id.lower() if next_id else None
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
                
                    # ==== 将收集到的旧链表转换为新数组 ====
                    if legacy_locks:
                        visited = set()
                        chains_to_create = []
                        for mid in list(legacy_locks.keys()):
                            if mid in visited: continue
                            # 回溯找头
                            curr = mid
                            path_visited = set()
                            while legacy_locks.get(curr) and legacy_locks[curr]['prev']:
                                prev_id = legacy_locks[curr]['prev']
                                if prev_id in path_visited: break
                                path_visited.add(prev_id)
                                curr = prev_id
                                
                            head = curr
                            chain = []
                            curr = head
                            path_visited = set()
                            while curr:
                                if curr in path_visited: break
                                path_visited.add(curr)
                                chain.append(curr)
                                visited.add(curr)
                                curr = legacy_locks.get(curr, {}).get('next')
                                
                            if len(chain) > 1:
                                chains_to_create.append(chain)
                        
                        # 写入新表并为 batch_data 注入 interlock_id
                        for chain in chains_to_create:
                            new_id = uuid.uuid4().hex
                            ModInterlock.create(id=new_id, chain=chain)
                            # 给准备 upsert 的 batch_data 打上标记
                            for cd in batch_data:
                                if cd['mod_id'].lower() in chain:
                                    cd['interlock_id'] = new_id
                    
                    # 调用 DAO 写入
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
                        new_group = GroupDAO.create_group(g_name, g.get('color', '#ffffff')) # type: ignore
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

                # =================================================
                # 4. 联锁组导入
                # =================================================
                imported_interlocks = env.get("interlocks", [])
                if imported_interlocks:
                    # 使用 insert_many().on_conflict_replace()，如果 ID 重复直接覆盖
                    for batch in chunked(imported_interlocks, 100):
                        ModInterlock.insert_many(batch).on_conflict_replace().execute()
                
            # 事务结束，保存文件
            self.save_user_rules()
            logger.info("Import bundle processed successfully.")
            for warning in import_warnings:
                logger.warning(warning)
            return {"warnings": import_warnings}

        except Exception as e:
            logger.error(f"Failed to process import bundle: {e}", exc_info=True)
            # 抛出异常让上层 API 捕获并返回错误信息给前端
            raise Exception(f"Import Error: {str(e)}")
    
    
    
