# backend/ai/tools.py

import json
import os
import re
from backend.database.dao import ModDAO, GroupDAO
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileContext
from backend.managers.mgr_game_logs import LogCondenser
from backend.settings import DATA_DIR
from backend.utils.logger import logger

class AIToolExecutor:
    """
    AI 工具执行器 (注册表模式)
    一次定义工具的 AI 描述、参数结构和执行方法。
    """
    
    _AI_MOD_INFO_SIMPLE_FIELDS = (
        'package_id',
        'name',
        'workshop_id',
        'supported_versions',
        'is_active',
        'path',
    )

    _AI_MOD_INFO_ALLOWED_FIELDS = (
        'package_id',
        'name',
        'author',
        'workshop_id',
        'version',
        'description',
        'path',
        'url',
        'source',
        'store',
        'supported_versions',
        'supported_languages',
        'mod_type',
        'is_active',
        'dependencies_mods',
        'load_after_mods',
        'load_before_mods',
        'incompatible_mods',
        'save_breaking',
        'last_active_time',
        'last_moved_time',
    )
    
    def __init__(self, active_context: ProfileContext, payload: dict, reader):
        self.context = active_context
        self.payload = payload
        self.reader = reader
        
        # 预加载：缓存一份当前已激活的 Mod ID 集合，供各个工具复用
        self._active_mod_ids_set = self._get_active_mod_id_set()

        # =====================================================================
        # 核心：工具注册表 (Tool Registry)
        # 生成 Schema 和 路由执行 全部依赖于此
        # =====================================================================
        self.registry = {
            "get_log_context": {
                "description": "获取指定错误日志的详细上下文（包含完整错误信息和核心堆栈）。仅当摘要中的 stack_preview 无法让你得出结论时才使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_line": {
                            "type": "integer",
                            "description": "【必须】只能传入一个代表行号。必须是错误摘要 (error_table_of_contents) 中提供的 target_line 数值，绝不能是 repeat_count 或其他不存在的行号！"
                        },
                        "stack_excerpt_lines": {
                            "type": "integer",
                            "description": "【可选】指定需要获取的堆栈最大行数。默认 15 行。如果你认为堆栈被截断了，可以增加此值（最大 80 行）。"
                        }
                    },
                    "required": ["target_line"],
                    "additionalProperties": False  # 严禁 AI 编造额外的参数
                },
                "method": self._tool_get_log_context
            },
            "search_mods": {
                "description": "当且仅当你不确定某个 Mod 的准确 package_id 时，使用此工具模糊搜索。可输入名字、别名或部分 ID 查找可能对应的 package_id。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词，例如 'RimFridge' 或 'Harmony'"}
                    },
                    "required": ["keyword"]
                },
                "method": self._tool_search_mods
            },
            "get_active_mod_list": {
                "description": "获取当前排序文件中的已激活模组列表，用于宏观检查模组顺序，返回模组包名列表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_names": {"type": "boolean", "description": "是否附带具体名称。体积较大，非必要传 false。"}
                    }
                },
                "method": self._tool_get_active_mod_list
            },
            "get_mod_info": {
                "description": f"获取当前环境中已安装模组的元数据。simple 返回基本必要信息：{self._AI_MOD_INFO_SIMPLE_FIELDS}。all 返回全部信息；specific 返回可选字段信息：{self._AI_MOD_INFO_ALLOWED_FIELDS}。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string", "description": "模组的包名，全小写，如 ludeon.rimworld"},
                        "scope": {
                            "type": "string",
                            "enum": ["simple", "all", "specific"],
                            "description": "信息范围：simple(必要字段), all(允许全部字段), specific(指定字段)"
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(self._AI_MOD_INFO_ALLOWED_FIELDS)},
                            "description": "当 scope 为 specific 时，指定要请求的字段。"
                        }
                    },
                    "required": ["package_id"]
                },
                "method": self._tool_get_mod_info
            },
            "get_mod_rules": {
                "description": "获取该模组的依赖模组、前置/后置模组和不兼容模组规则，以了解该模组与其它模组之间的显性关系。只有在怀疑缺失前置、加载顺序错误或存在不兼容模组时再调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                        "native_only": {
                            "type": "boolean",
                            "description": "true=仅获取Mod作者原生写入About.xml的规则；false=获取合并了社区和玩家自定义后的最终生效规则"
                        }
                    },
                    "required": ["package_id"]
                },
                "method": self._tool_get_mod_rules
            },
            "get_mod_user_data": {
                "description": "获取该已安装模组在管理器中的用户态上下文：别名、标签、备注、颜色、自定义类型和所属分组。这些信息只用于辅助理解玩家归类，属于模组管理器专有信息，与游戏机制无关。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"}
                    },
                    "required": ["package_id"]
                },
                "method": self._tool_get_mod_user_data
            },
            "get_group_mods": {
                "description": "按分组名查询分组所含模组。分组信息只用于辅助理解玩家归类，属于模组管理器专有信息，与游戏机制无关。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "group_name": {"type": "string", "description": "要查询的分组名，支持模糊匹配。"}
                    },
                    "required": ["group_name"]
                },
                "method": self._tool_get_group_mods
            }
        }

    # =====================================================================
    # 外部接口：供 AIManager 调用
    # =====================================================================

    def get_tool_schemas(self, enabled_names: list = []) -> list:
        """
        动态生成大模型所需的 OpenAI/LiteLLM 标准 JSON Schema 结构。
        :param enabled_names: 前端传来的启用工具名称列表，如果为空则返回全部
        """
        schemas = []
        for name, config in self.registry.items():
            # 过滤未启用的工具
            if enabled_names and name not in enabled_names: continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": config["description"],
                    "parameters": config["parameters"]
                }
            })
        return schemas

    def execute(self, name: str, arguments_str: str) -> str:
        """
        统一的工具执行路由，直接查字典执行。
        """
        try:
            args = json.loads(arguments_str) if arguments_str else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "参数解析失败(Invalid JSON)"}, ensure_ascii=False)

        if name not in self.registry:
            return json.dumps({"error": f"系统未注册此工具: {name}"}, ensure_ascii=False)

        try:
            logger.debug(f"[AI诊断] 开始执行工具 name={name} args={args}")
            # 【核心】直接从字典取出 method 并执行
            result_str = self.registry[name]["method"](args)
            return result_str
        except Exception as e:
            logger.error(f"AI工具执行异常 [{name}]: {str(e)}", exc_info=True)
            return json.dumps({"error": f"工具执行内部异常: {str(e)}"}, ensure_ascii=False)

    # =====================================================================
    # 具体的工具实现方法 (Methods)
    # =====================================================================
    
    def _clean_rich_text_for_ai(self, text: str | None, max_length: int = 1000) -> str:
        """对 Mod 描述做与前端 cleanRichText 类似的清洗，降低 AI 噪音。"""
        if not text: return ""
        clean = str(text)
        clean = re.sub(r'<[^>]+>', '', clean)
        clean = re.sub(r'\[url=[^\]]*\]([^\[]+)\[/url\]', r'\1', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\[[^\]]+\]', '', clean)
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        clean = re.sub(r'(https?|ftp):\/\/[^\s/$.?#].[^\s]*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s{2,}', ' ', clean)
        clean = re.sub(r'\n+', '\n', clean).strip()
        if len(clean) > max_length: clean = clean[:max_length] + "..."
        return clean
    
    def _get_active_mod_id_set(self) -> set:
        """辅助方法：返回当前启用列表中的 package_id 集合"""
        if not self.context: return set()
        lo_mgr = LoadOrderManager(self.context)
        return set(pid.lower() for pid in lo_mgr.read_active_mods().get('active_mods', []))

    def _tool_get_log_context(self, args: dict) -> str:
        """获取指定行号的日志上下文，包含完整调用栈。"""
        # 1. 严格提取唯一的 target_line
        try:
            target_line = int(args.get("target_line", 0))
        except (TypeError, ValueError):
            target_line = 0
        if target_line <= 0:
            return json.dumps({"error": "必须提供有效的 target_line 参数（必须大于0的整数）。"}, ensure_ascii=False)
        
        # 2. 提取 AI 决定的堆栈深度，限制在合理范围内 (6 到 80 行)
        try:
            stack_excerpt_lines = int(args.get("stack_excerpt_lines", 15))
            stack_excerpt_lines = max(6, min(stack_excerpt_lines, 80))
        except (TypeError, ValueError):
            stack_excerpt_lines = 15

        # 3. 获取文件路径和 reader
        source_type = self.payload.get("log_source_type", "game") if self.payload else "game"
        filename = self.payload.get("filename", "") if self.payload else ""
        if not filename:
            return json.dumps({"error": "前端未提供当前日志文件名 filename。"}, ensure_ascii=False)
        if source_type == 'game':
            filepath = os.path.join(self.context.user_data_path, filename) if self.context else ""
        else:
            filepath = os.path.join(DATA_DIR, 'logs', filename)
        if not os.path.exists(filepath):
            return json.dumps({"error": f"找不到对应日志文件: {filename}"}, ensure_ascii=False)
        if not self.reader or not hasattr(self.reader, "get_raw_logs_by_lines"):
            return json.dumps({"error": "当前日志读取器不支持按行反查日志块"}, ensure_ascii=False)

        # 4. 执行反查（传入 [target_line] 单元素列表复用底层接口）
        matched_blocks = self.reader.get_raw_logs_by_lines(filepath, [target_line])
        
        # 5. 精确匹配包含该 target_line 的日志块
        target_block = None
        for block in matched_blocks:
            # 将 raw_lines 转为整数列表进行安全对比
            raw_lines = []
            for raw_value in block.get("raw_lines", []):
                try:
                    raw_lines.append(int(raw_value))
                except (TypeError, ValueError):
                    continue
            if target_line in raw_lines:
                target_block = block
                break
        # 兜底：如果没精确匹配到行号，但这个文件确实返回了块（可能是日志滚动导致行号偏移）
        if target_block is None and matched_blocks:
            target_block = matched_blocks[0]
        if target_block is None:
            logger.debug(f"[AI诊断] get_log_context 未命中日志块 filename={filename} target_line={target_line}")
            return json.dumps({
                "error": f"无法定位请求的代表行号 #{target_line}。该错误可能已被折叠或文件已变更。"
            }, ensure_ascii=False)
        
        # 6. 提炼极其纯净的上下文给 AI，绝对不暴露 raw_lines 数组等让它困惑的数据
        level = str(target_block.get("level", "INFO") or "INFO")
        message = str(target_block.get("message", "") or "").strip()
        details = str(target_block.get("details", "") or "").strip()
        repeat_count = int(target_block.get("count", 1) or 1)
        # 按 AI 要求裁剪堆栈
        cleaned_details = LogCondenser.clean_stack_trace(details, max_lines=stack_excerpt_lines)
        context_sections = [f"[日志内容 | 代表行号 #{target_line}] {level}: {message}"]
        if cleaned_details:
            context_sections.append(f"[堆栈详情 (截取前 {stack_excerpt_lines} 行)]")
            context_sections.append(cleaned_details)
        elif details:
            context_sections.append("[堆栈详情 (原始内容)]")
            context_sections.append(details)
        # 组装返回的纯净结构
        result_payload = {
            "representative_line": target_line,
            "total_repeats": repeat_count,
            "stack_excerpt_lines_provided": stack_excerpt_lines if details else 0,
            "context_content": "\n".join(section for section in context_sections if section)
        }
        logger.debug(f"[AI诊断] get_log_context 命中 filename={filename} target_line={target_line} stack_excerpt_lines={stack_excerpt_lines}")
        return json.dumps(result_payload, ensure_ascii=False)

    def _tool_get_active_mod_list(self, args: dict) -> str:
        """获取当前激活的模组列表，可选择是否包含模组名称。"""
        include_names = args.get("include_names", False)
        lo_mgr = LoadOrderManager(self.context)
        mods_data = lo_mgr.read_active_mods().get('mods', [])
        if include_names:
            active_list = {m.get('package_id', ''): m.get('name', '') for m in mods_data}
        else:
            active_list = [m.get('package_id', '') for m in mods_data]
        return json.dumps({"total_active": len(mods_data), "active_order": active_list}, ensure_ascii=False)

    def _tool_search_mods(self, args: dict) -> str:
        """
        根据关键词搜索可见的模组，返回匹配结果。
        匹配范围：package_id / workshop_id / name / alias_name / author
        """
        keyword = str(args.get("keyword", "") or "").strip()
        if not keyword: return json.dumps({"error": "必须提供 keyword"})
        needle = str(keyword or '').strip().lower()
        if not needle: return json.dumps({"keyword": keyword, "matched": []}, ensure_ascii=False)
        active_ids = self._active_mod_ids_set
        limit = int(args.get("limit", 10) or 10)
        def _score_field(value: str, reason: str):
            '''计算字段值的匹配分数和原因。'''
            text = value.strip().lower()
            if not text: return 0, None
            if text == needle: return 120, reason
            if text.startswith(needle): return 90, reason
            if needle in text: return 60, reason
            return 0, None

        results = []
        for mod in ModDAO.get_profile_mods(self.context):
            name = str(mod.get('name') or '').strip()
            package_id = str(mod.get('package_id') or '').strip().lower()
            workshop_id = str(mod.get('workshop_id') or '').strip().lower()
            alias_name = str(mod.get('alias_name') or '').strip()
            authors = [str(author).strip() for author in (mod.get('author') or []) if str(author).strip()]
            score = 0
            reasons = []
            for value, reason in (
                (package_id, 'package_id'),
                (workshop_id, 'workshop_id'),
                (name, 'name'),
                (alias_name, 'alias_name'),
            ):
                field_score, match_reason = _score_field(value, reason)
                if field_score > score: score = field_score
                if match_reason and match_reason not in reasons: reasons.append(match_reason)
            for author in authors:
                field_score, match_reason = _score_field(author, 'author')
                if field_score > score: score = field_score
                if match_reason and match_reason not in reasons: reasons.append(match_reason)
            if score <= 0: continue
            results.append({
                'package_id': package_id,
                'workshop_id': workshop_id or None,
                'name': name,
                'alias_name': alias_name or None,
                'author': authors,
                'is_active': package_id in active_ids,
                'match_reason': reasons,
                '_score': score,
            })
        results.sort(key=lambda item: (-item.get('_score', 0), item.get('name') or item.get('package_id') or ''))
        trimmed = results[:max(1, limit)]
        for item in trimmed: 
            item.pop('_score', None)
        
        return json.dumps({"keyword": keyword, "matched": trimmed}, ensure_ascii=False)

    def _tool_get_mod_info(self, args: dict) -> str:
        """获取指定模组的详细信息，可选择返回范围和字段。"""
        pkg_id = args.get("package_id", "").lower()
        if not pkg_id: return json.dumps({"error": "必须提供有效的 package_id"})
        mod = ModDAO.get_visible_profile_mod(self.context, pkg_id)
        if not mod: return json.dumps({"error": f"当前环境中未找到此模组: {pkg_id}"})
        scope = str(args.get("scope", "simple") or "simple").lower()
        fields = args.get("fields", [])
        # 1. 初始化安全的返回数据结构
        safe_mod = {}
        for field_name in self._AI_MOD_INFO_ALLOWED_FIELDS:
            value = mod.get(field_name)
            if field_name == 'description':
                value = self._clean_rich_text_for_ai(value, max_length=1000)
            elif field_name == 'is_active':
                value = pkg_id in self._active_mod_ids_set
            safe_mod[field_name] = value
        # 2. 处理请求的字段
        requested_fields = []
        for field_name in fields or []:
            normalized = str(field_name or '').strip()
            if normalized and normalized not in requested_fields:
                requested_fields.append(normalized)
        # 3. 根据 scope 处理字段选择
        if scope == 'all':
            selected_fields = list(self._AI_MOD_INFO_ALLOWED_FIELDS)
            invalid_fields = []
        elif scope == 'specific':
            selected_fields = [field_name for field_name in requested_fields if field_name in self._AI_MOD_INFO_ALLOWED_FIELDS]
            invalid_fields = [field_name for field_name in requested_fields if field_name not in self._AI_MOD_INFO_ALLOWED_FIELDS]
            if not selected_fields:
                result =  {
                    "error": "specific 模式至少需要一个合法字段",
                    "package_id": pkg_id,
                    "supported_fields": list(self._AI_MOD_INFO_ALLOWED_FIELDS),
                    "invalid_fields": invalid_fields,
                }
                return json.dumps(result, ensure_ascii=False)
        else:
            scope = 'simple'
            selected_fields = list(self._AI_MOD_INFO_SIMPLE_FIELDS)
            invalid_fields = []

        data = {field_name: safe_mod.get(field_name) for field_name in selected_fields}
        result =  {
            "package_id": pkg_id,
            "scope": scope,
            "returned_fields": selected_fields,
            "invalid_fields": invalid_fields,
            "data": data,
        }
        return json.dumps(result, ensure_ascii=False)

    def _tool_get_mod_rules(self, args: dict) -> str:
        """获取指定模组的生效规则，可选择是否仅返回原生规则。"""
        pkg_id = args.get("package_id", "").lower()
        native_only = args.get("native_only", False)
        mod = ModDAO.get_visible_profile_mod(self.context, pkg_id)
        if not mod: return json.dumps({"error": f"未找到此模组: {pkg_id}"})
        if native_only:
            return json.dumps({
                "dependencies": mod.get("dependencies_mods", []),
                "load_after": mod.get("load_after_mods", []),
                "load_before": mod.get("load_before_mods", []),
                "incompatible": mod.get("incompatible_mods", [])
            }, ensure_ascii=False)
        else:
            # 获取经过管理器合并后的真实生效规则
            from backend.managers.mgr_rules import RuleManager
            effective_rules = RuleManager(self.context).get_effective_mod_rules(pkg_id, mod)
            return json.dumps(effective_rules, ensure_ascii=False)

    def _tool_get_mod_user_data(self, args: dict) -> str:
        """获取指定模组的用户自定义信息，。"""
        pkg_id = args.get("package_id", "").lower()
        if not pkg_id: return json.dumps({"error": "必须提供有效的 package_id"})
        mod = ModDAO.get_visible_profile_mod(self.context, pkg_id)
        if not mod: return json.dumps({"error": f"当前环境中未找到此模组: {pkg_id}"})
        result = {
            "package_id": pkg_id,
            "alias_name": mod.get("alias_name", mod.get("name")),
            "tags": mod.get("tags", []),
            "groups": mod.get("groups", []),
            "notes": str(mod.get("notes") or "").strip() or None,
            "sign_color": mod.get("sign_color"),
            "mod_type": mod.get("user_mod_type", mod.get("mod_type")),
        }
        
        return json.dumps(result, ensure_ascii=False)

    def _tool_get_group_mods(self, args: dict) -> str:
        """获取指定分组的模组列表，可选择返回范围和字段。"""
        group_name = args.get("group_name", "").strip()
        if not group_name: return json.dumps({"error": "必须提供有效的 group_name"})
        limit = int(args.get("limit", 40))
        visible_mods = ModDAO.get_profile_mods(self.context)
        active_ids = self._active_mod_ids_set
        visible_map = {
            str(mod.get('package_id') or '').strip().lower(): mod
            for mod in visible_mods
            if str(mod.get('package_id') or '').strip()
        }
        if not visible_map: return json.dumps({"matched_groups": []})
        
        groups = GroupDAO.get_groups_structured_by_mod_ids(list(visible_map.keys()))
        matched_groups = []
        for group in groups:
            name = str(group.get('name') or '').strip()
            if not name or group_name.lower() not in name.lower(): continue
            mods = []
            for mod_id in group.get('mod_ids', []) or []:
                pid = str(mod_id or '').strip().lower()
                mod = visible_map.get(pid)
                if not mod: continue
                mods.append({ "package_id": pid, "name": mod.get("name"), "is_active": pid in active_ids, })
            matched_groups.append({
                "group_name": name,
                "color": group.get("color"),
                "mod_count": len(mods),
                "mods": mods[:max(1, limit)],
                "truncated": len(mods) > max(1, limit),
            })

        result = {
            "keyword": group_name,
            "matched_groups": matched_groups,
        }
        return json.dumps(result, ensure_ascii=False)
    


