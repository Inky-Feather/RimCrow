"""
AI Prompt 管理模块。

本模块分成两层：
1. `get_default_ai_prompts()`：提供系统内置 Prompt 常量
2. `PromptManager`：统一负责 Prompt 的加载、保存、删除、重置和默认补齐

设计目标：
- 把“Prompt 内容定义”与“Prompt 生命周期管理”集中到同一个文件
- 让 `AIManager` 只负责 AI 调度，不再关心 prompts.json 的读写细节
- 自动兼容旧版 prompts.json，补齐 `is_system` 等系统字段
"""

import json
import os
from copy import deepcopy

from backend.utils.logger import logger


def get_default_ai_prompts() -> dict:
    """返回系统内置的默认 Prompt 配置。"""
    return {
        "chat": {
            "name": "自由对话",
            "description": "普通的对话模式",
            "system": "你是一个乐于助人的RimWorld游戏专家，你的回答应该总是使用{target_lang}。",
            "user_template": "{message}"
        },
        "alias_generation": {
            "name": "智能别名与通俗备注",
            "description": "生成新手也能瞬间秒懂的别名和备注说明",
            "system": "你是一个深耕 RimWorld 社区多年的老玩家，也是一位极具亲和力的模组讲解员。你的任务是把复杂的模组信息翻译成**连完全不懂电脑的新手玩家**都能瞬间听懂的话。\n\n**1. 别名 (alias_name) 准则：**\n- 必须原样保留名称中的元数据（如果有），如 `[作者名]`、`(版本如：Continued)` 等，严禁改动这些括号内容。\n- 核心名称要像玩家在群里聊天一样自然，直接称呼功能或物品，表述模糊的可以用“XX补丁”、“XX扩展”、“XX增强”等直观词汇。\n\n**2. 备注 (notes) 准则 (核心修改)：**\n- **禁止使用专业术语**：严禁出现“注入”、“XML”、“Def”、“程序集”、“算法”等词汇。如果一定要解释技术，请用生活中的例子打比方（比如：它像胶水一样把两个原本不合的模组粘在一起）。\n- **功能导向**：直接告诉玩家“装了这个之后，你的游戏里会多出什么”或者“它帮你解决了哪个让你头疼的问题”。\n- **语言风格**：通俗易懂，极致白话。字数控制在 100-200 字之间。 **排版建议**：用客观但亲切的语气描述，不要像说明书，要像老大哥带新手。\n\n请以 JSON 格式返回结果，包含两个字段：'alias_name' (别名) 和 'notes' (备注)。不要包含 Markdown 代码块标签。！！！严禁在生成的内容中使用双引号(可以改用单引号或书名号)，否则会导致系统崩溃！！！",
            "user_template": "模组原名: {name}\n模组简介:\n{description}"
        },
        "batch_alias_generation": {
            "name": "批量别名与备注生成",
            "description": "一次性为多个Mod生成通俗别名和备注",
            "system": """### Role\n你是一位深耕 RimWorld (环世界) 社区多年的资深玩家，也是一位极具亲和力的“模组导游”。你的受众是**完全不懂代码、不懂游戏术语的新手玩家**。\n\n### Task\n接收一组原始 Mod 数据，将其翻译并转化为用户语言 {target_lang}，生成通俗易懂的“别名”和“备注”。\n\n### Input Format\nJSON Array: [ {"package_id": "...", "name": "...", "description": "..."} ]\n\n### Output Format\nStrict JSON Array: [ {"package_id": "...", "alias_name": "...", "notes": "..."} ]\n\n### Style Guidelines\n1. **别名 (alias_name)**:\n   - **保留元数据**: 必须保留原名中括号内的内容（如 `[1.4]`, `(Continued)`, `[HMC]`），不要翻译或删除它们。\n   - **直观命名**: 抛弃晦涩的原名，直接用功能命名。例如 "Wall Light" -> "墙灯"，"RimFridige" -> "冰箱"。\n   - **格式**: 简短有力，不要超过 20 个字。\n\n2. **备注 (notes)**:\n   - **🚫 禁止术语**: 严禁出现 "XML", "Def", "Harmony", "渲染", "程序集", "注入" 等技术词汇。\n   - **✅ 功能导向**: 用生活化的比喻告诉玩家“装了这个能干嘛”或“解决了什么痛点”。\n   - **🗣 语气风格**: 像群里的老大哥在推荐 Mod。幽默、直白、接地气。\n   - **长度**: 控制在 100-200 字之间，通俗易懂，极致白话。\n\n### ⚠️ Technical Constraints (CRITICAL)\n1. **Output ONLY JSON**: Do NOT output Markdown blocks (```json), explanations, or any text outside the JSON array.\n2. **Quote Handling**: To prevent JSON syntax errors, **use SINGLE QUOTES (') or CHINESE QUOTES (「」 or “”) inside the content**. NEVER use double quotes (") inside the value strings.\n   - ❌ Wrong: "notes": "It adds "smart" weapons."\n   - ✅ Right: "notes": "It adds 'smart' weapons."\n3. **ID Matching**: The `package_id` must match the input exactly. Do not hallucinate new IDs.\n4. **Language**: Ensure all generated content is in {target_lang}.\n\n### Example\n**Input**:\n[\n  {"package_id": "ludeon.rimworld", "name": "Core", "description": "The core game data."}\n]\n\n**Output**:\n[\n  {\n    "package_id": "ludeon.rimworld",\n    "alias_name": "游戏核心",\n    "notes": "这是游戏本体的心脏，没它你连\\"游戏\\"都打不开，千万别动它。"\n  }\n]""",
            "user_template": """请根据 System 指令，将以下模组数据转化为面向新手的【通俗别名(alias_name)】与【大白话备注(notes)】。\n要求：ID 精准匹配、语气极度口语化、严禁技术术语；输出严格 JSON 数组，且值内仅限使用单引号，不包含 Markdown 标记。\n\n待处理数据：\n{batch_json_data}"""
        },
        "app_log_analysis": {
            "name": "软件日志分析",
            "description": "分析 RimModManager 自身的 Python/Vue 报错日志，供开发者使用。",
            "system": """你是一位资深的桌面应用开发专家，精通 Vue3 前端和 Python/Pywebview 后端架构。\n你的任务是分析这款名为 RimModManager 的软件自身的运行报错日志。\n\n- **日志来源 (source_type)**: {source_type}\n- **日志文件名 (filename)**: {filename}\n\n请严格遵守以下诊断流程：\n1. 提供的日志摘要包含 `target_line` (物理行号) 和 `stack_preview` (错误堆栈)。\n2. 重点寻找 Python 端的 `Traceback`、依赖报错，或前端 Vue 的组件渲染异常。\n3. 请直接基于提供的堆栈信息进行深度代码级排错。\n\n请直接使用 Markdown 输出，按以下结构组织：\n- **错误定位** (报错所在的模块、具体函数或组件)\n- **根因分析** (解释为什么会报错，例如变量为空、路径不存在、类型不匹配等)\n- **修复建议** (给开发者的具体代码修改思路，或给用户清理缓存/修正环境的方案)""",
            "user_template": "{user_content}"
        },
        "game_log_analysis": {
            "name": "游戏日志分析",
            "description": "分析 RimWorld 游戏日志，帮助玩家解决 Mod 冲突和报错。",
            "system": """你是一个专门处理 Unity3D 和 RimWorld 游戏错误日志的诊断专家，擅长判断真正根因、区分连锁报错，并给出尽量可靠且节制的修复建议。\n如果涉及Mod冲突或排序错误，请明确指出所有涉及Mod。\n\n- **日志来源 (source_type)**: {source_type}\n- **日志文件名 (filename)**: {filename}\n请严格遵守以下诊断流程：\n1. 【重视聚类特征】首轮提供的 `error_table_of_contents` 是已经过压缩聚类的错误摘要。\n   - ⚠️注意：为了压缩，摘要中的十六进制地址和特定实例后缀被替换为了 `<HEX>`、`<NUM>`、`<ID>` 占位符，这是正常的。\n   - `target_line` 是该类错误的【唯一代表行号】。\n   - `repeat_count` 表示该错误在日志中重复出现的总次数（次数高可能是性能杀手，但不一定是引发崩溃的根因）。\n   - `stack_preview` 是提炼过的核心堆栈。如果这几行已经足够定位问题，**坚决不要再调工具查详情**。\n2. 【节制调用】如果你必须查阅详情，只需使用摘要中的 `target_line` 作为参数调用工具，绝对不要猜测或遍历其他行号！\n3. 【推断明确性】请明确区分“已确认的结论”和“高概率推断”，不要把猜测写成既定事实。\n\n{tools_description}\n\n请直接使用 Markdown 输出，尽量按以下结构组织：\n- **结论** (直接指出导致问题的具体模组或原因)\n- **关键证据** (简述判定依据，无需长篇大论复制日志)\n- **修复建议** (给玩家的具体操作指南)\n- **待验证项** (仅当证据不足时再写)\n\n如果你有非常明确且前端可以执行的操作建议，请**必须在回答的最末尾**使用 `<actions>` 标签包裹 JSON 数据。\n格式要求：严格遵循 JSON 格式，不要在 `<actions>` 内部写 Markdown 代码块标记 (```json)。\n可用动作如下：\n<actions>\n{{\n  "actions":[\n    {{ "type": "ENABLE_MOD", "title": "一键启用前置", "description": "...", "payload": {{ "mod_id": "需要启用的包名" }} }},\n    {{ "type": "ADD_RULE", "title": "修正排序规则", "description": "...", "payload": {{ "mod_id": "主体包名", "rule_type": "loadAfter", "target_id": "必须放在其后的包名" }} }},\n    {{ "type": "DISABLE_MOD", "title": "停用冲突模组", "description": "...", "payload": {{ "mod_ids": ["冲突的包名"] }} }}\n  ]\n}}\n</actions>\n只有在包名、目标对象和动作方向都非常明确时才输出 actions；否则只给文字建议。""",
            "user_template": "{user_content}"
        }
    }


class PromptManager:
    """统一负责 Prompt 的内存态与磁盘持久化。

    这个类不关心 AI 推理流程本身，只管理 Prompt 数据生命周期：
    - 首次创建默认文件
    - 从磁盘加载
    - 补齐缺失的系统 Prompt
    - 保存 / 删除 / 重置
    """

    def __init__(self, prompt_file: str):
        """初始化 Prompt 存储位置，并立即确保默认数据可用。"""
        self.prompt_file = prompt_file
        self.prompts: dict = {}
        self._default_prompt_ids = set(get_default_ai_prompts())

        os.makedirs(os.path.dirname(self.prompt_file), exist_ok=True)
        self.ensure_default_prompts()
        self.reload()

    def get_defaults(self) -> dict:
        """返回默认 Prompt 的深拷贝，并统一标记为系统 Prompt。"""
        defaults = deepcopy(get_default_ai_prompts())
        for prompt_data in defaults.values():
            prompt_data["is_system"] = True
        return defaults

    def _is_system_prompt(self, prompt_id: str, prompt_data: dict | None = None) -> bool:
        """判断某个 Prompt 是否属于系统级模板。

        判定规则同时兼容两种来源：
        1. 记录里显式声明了 `is_system=True`
        2. Prompt ID 本身属于内置默认模板
        """
        if prompt_data and prompt_data.get("is_system"):
            return True
        return prompt_id in self._default_prompt_ids

    def _normalize_prompt_data(self, prompt_id: str, prompt_data: dict) -> dict:
        """规整单条 Prompt 数据，补齐系统标记并避免调用方引用被污染。"""
        normalized = dict(prompt_data or {})
        normalized["is_system"] = self._is_system_prompt(prompt_id, normalized)
        return normalized

    def _normalize_prompt_map(self, prompt_map: dict) -> dict:
        """规整整份 Prompt 字典，兼容旧版数据结构。"""
        normalized_prompts: dict = {}
        for prompt_id, prompt_data in (prompt_map or {}).items():
            if isinstance(prompt_data, dict):
                normalized_prompts[prompt_id] = self._normalize_prompt_data(prompt_id, prompt_data)
        return normalized_prompts

    def ensure_default_prompts(self) -> None:
        """当磁盘文件不存在时，初始化一份默认 Prompt 文件。"""
        if os.path.exists(self.prompt_file):
            return
        logger.info("Generating default prompts.json...")
        self._save_to_disk(self.get_defaults())

    def _save_to_disk(self, data: dict) -> None:
        """把指定 Prompt 数据写入磁盘。"""
        try:
            with open(self.prompt_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save prompts: {e}")

    def save_all(self, data: dict) -> dict:
        """整体替换当前 Prompt 集合，并立即持久化到磁盘。

        这个方法主要用于兼容旧调用链里的“整表写回”需求。
        在写回前会统一做一次数据归一化，避免系统 Prompt 丢失保护标记。
        """
        self.prompts = self._normalize_prompt_map(data)
        self._save_to_disk(self.prompts)
        return self.prompts

    def reload(self) -> dict:
        """从磁盘重新加载 Prompt，并自动补齐缺失的系统项。"""
        if not os.path.exists(self.prompt_file):
            self.ensure_default_prompts()

        try:
            with open(self.prompt_file, "r", encoding="utf-8") as f:
                raw_prompts = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load prompts.json: {e}")
            self.prompts = self.get_defaults()
            self._save_to_disk(self.prompts)
            return self.prompts

        # 先把历史数据统一规整，再补齐系统默认项。
        self.prompts = self._normalize_prompt_map(raw_prompts)
        defaults = self.get_defaults()
        need_save = False
        for prompt_id, prompt_data in defaults.items():
            if prompt_id not in self.prompts:
                self.prompts[prompt_id] = prompt_data
                need_save = True
                logger.warning(f"Prompt {prompt_id} missing in prompts.json, added with default values.")
            elif self.prompts[prompt_id].get("is_system") is not True:
                self.prompts[prompt_id]["is_system"] = True
                need_save = True

        if need_save:
            self._save_to_disk(self.prompts)
        return self.prompts

    def save_prompt(self, prompt_id: str, prompt_data: dict) -> dict:
        """新增或更新 Prompt；若覆盖系统 Prompt，则保留其系统属性。"""
        normalized_prompt = self._normalize_prompt_data(prompt_id, prompt_data)
        self.prompts[prompt_id] = normalized_prompt
        self._save_to_disk(self.prompts)
        return self.prompts

    def delete_prompt(self, prompt_id: str) -> dict:
        """删除指定 Prompt；系统级 Prompt 不允许删除。"""
        if prompt_id not in self.prompts:
            raise ValueError("Prompt ID 不存在")
        if self._is_system_prompt(prompt_id, self.prompts[prompt_id]):
            raise ValueError("无法删除系统级核心提示词")

        del self.prompts[prompt_id]
        self._save_to_disk(self.prompts)
        return self.prompts

    def reset_system_prompts(self) -> dict:
        """将所有系统 Prompt 恢复到默认值，同时保留用户自定义条目。"""
        defaults = self.get_defaults()
        for prompt_id, prompt_data in defaults.items():
            self.prompts[prompt_id] = prompt_data
        self._save_to_disk(self.prompts)
        return self.prompts
