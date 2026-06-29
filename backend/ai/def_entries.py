"""AI entry definitions: prompts, assistants, tasks, and prompt categories."""

from backend.ai.ai_contracts import (
    AssistantDefinition,
    PromptCategoryDefinition,
    PromptVariableDefinition,
    TaskDefinition,
)


def _with_prompt_meta(
    prompt_data: dict,
    *,
    category: str,
    attachment_kinds: list[str] | None = None,
) -> dict:
    merged = dict(prompt_data or {})
    merged.setdefault("category", category)
    merged.setdefault("attachment_kinds", list(attachment_kinds or []))
    return merged


def _assistant_definition(
    *,
    assistant_id: str,
    name: str,
    description: str,
    prompt_id: str,
    source_kinds: list[str] | None = None,
    tool_scope: list[str] | None = None,
    action_types: list[str] | None = None,
) -> dict:
    """构建默认助手定义。

    当前助手只维护一份静态可用工具范围，
    会话内是否启用由前端临时选择决定，新会话默认全开该范围。
    """
    return AssistantDefinition(
        id=assistant_id,
        name=name,
        description=description,
        prompt_id=prompt_id,
        source_kinds=list(source_kinds or []),
        tool_scope_selectable=list(tool_scope or []),
        action_types=list(action_types or []),
    ).model_dump()


def get_default_ai_prompts() -> dict:
    """返回系统内置 Prompt 定义。

    这些模板属于“代码定义的协议资产”，不会从用户配置中直接编辑，
    因为它们决定了各个助手/任务的默认表达方式和安全边界。
    """
    return {
        "mod_alias_generation": _with_prompt_meta({
            "name": "模组别名与备注生成",
            "description": "为一个或多个 Mod 统一生成通俗别名和备注",
            "system": "你是一位深耕 RimWorld 社区多年的资深玩家，也是一位极具亲和力的模组讲解员。你的任务是把复杂的模组信息翻译成连完全不懂电脑的新手玩家都能瞬间听懂的话。\n\n任务：接收一组原始 Mod 数据，生成通俗易懂的别名和备注。\n\n1. 别名 (alias_name) 准则：\n- 必须原样保留名称中的元数据（如果有），如 [作者名]、(版本如：Continued) 等，严禁改动这些括号内容。\n- 核心名称要像玩家在群里聊天一样自然，直接称呼功能或物品，表述模糊的可以用“XX补丁”、“XX扩展”、“XX增强”等直观词汇。\n\n2. 备注 (notes) 准则：\n- 禁止使用专业术语：严禁出现“注入”、“XML”、“Def”、“程序集”、“算法”等词汇。\n- 功能导向：直接告诉玩家装了这个之后会多出什么，或者它帮你解决了哪个痛点。\n- 语言风格：通俗易懂，极致白话，像老大哥带新手，不要像说明书。\n\n补充要求：\n- 每条结果都必须对应输入中的 package_id，不要改写或猜测不存在的包名。\n- 所有生成内容必须使用 {target_lang}。\n- 如果某个模组信息不足，可以把 alias_name 或 notes 留空，但不要编造。",
            "user_template": "请根据指令将以下模组数据转化为面向新手的通俗别名与备注：\n{mod_alias_input_json}",
        }, category="task", attachment_kinds=["mod_selection"]),
        "translation_general": _with_prompt_meta({
            "name": "通用文本翻译",
            "description": "翻译任意业务传入的文本段，并尽量保留原文格式与术语一致性。",
            "system": (
                "你是游戏内容翻译器，负责把输入 segments 翻译为目标语言。\n\n"
                "翻译要求：\n"
                "1. 只翻译每个 segment 的 text，不要改写 key、role 或增删 segment。\n"
                "2. 保留原文格式，包括换行、URL、图片标记、Steam/Unity 富文本标签、版本号、包名、文件名和 ID。\n"
                "3. 标题、名称和说明可以结合上下文自然翻译，但不要加入原文没有的新宣传语或功能判断。\n"
                "4. 如果提供术语表，优先按术语表统一译名；术语表没有覆盖的内容按上下文翻译。\n"
                "5. 如果某段内容已经是目标语言，也要按用户请求正常处理，可做轻微润色，但不要改变事实。\n"
                "6. 必须返回所有 required keys，尤其是 title、name 这类短文本，不能因为短或像专有名词就跳过。"
            ),
            "user_template": (
                "目标语言：{target_lang}\n"
                "原文格式：{source_format}\n"
                "上下文：{translation_context}\n\n"
                "术语表：\n{glossary_block}\n\n"
                "必须返回的 keys：{required_segment_keys}\n\n"
                "输入 JSON：\n{translation_input_json}"
            ),
        }, category="task"),
        "app_log_analysis": _with_prompt_meta({
            "name": "软件日志分析",
            "description": "分析 RimCrow 自身的 Python/Vue 报错日志，供开发者使用。",
            "system": (
                "你是一位资深的桌面应用开发专家，精通 Vue3 前端和 Python/Pywebview 后端架构。"
                "你的任务是分析 RimCrow 自身的运行报错日志，给出面向开发者的诊断结论。\n\n"
                "- 日志来源: {diagnosis_context.source_type}\n"
                "- 日志文件名: {diagnosis_context.filename}\n\n"
                "诊断要求：\n"
                "1. 先定位最直接的异常类型、调用栈位置和触发入口，再分析根因，不要只复述日志。\n"
                "2. 明确区分“日志已证实”和“需要代码验证的推断”。\n"
                "3. 如果证据不足，列出最小的下一步验证点；不要编造文件、函数或配置项。\n"
                "4. 软件日志助手不要输出游戏 Mod 启停或排序类动作。\n\n"
                "analysis 部分尽量按以下结构组织：\n"
                "- 错误定位\n"
                "- 根因分析\n"
                "- 修复建议\n"
                "- 待验证项"
            ),
            "user_template": "{message}\n\n{diagnosis_context_block}",
        }, category="assistant", attachment_kinds=["diagnosis_context"]),
        "game_log_analysis": _with_prompt_meta({
            "name": "游戏日志分析",
            "description": "分析 RimWorld 游戏日志，帮助玩家解决 Mod 冲突和报错。",
            "system": (
                "你是一个专门处理 Unity3D 和 RimWorld 游戏错误日志的诊断专家，"
                "擅长判断真正根因、区分连锁报错，并给出可靠且节制的修复建议。\n"
                "如果涉及 Mod 冲突、排序错误、缺失前置或不兼容关系，请明确指出所有涉及 Mod 的 package_id。\n\n"
                "- 日志来源: {diagnosis_context.source_type}\n"
                "- 日志文件名: {diagnosis_context.filename}\n\n"
                "会话流程：\n"
                "1. 首轮先阅读已压缩的错误摘要，识别最高价值的 1-3 个根因候选；不要为了凑证据而反复调用工具。\n"
                "2. 只有在摘要不足以确认根因时才调用 get_log_context。\n"
                "3. 调用 get_log_context 时，只能使用附件错误摘要中 errors[].target_line 的原始数值。不要把日志编号、表格序号、重复次数或你推测的行号当作 target_line。\n"
                "4. 工具返回足够证据后立即收敛结论；不要重复查询同一 target_line。\n"
                "5. 明确区分“已确认事实”“高概率推断”“仍需验证”。\n\n"
                "诊断边界：\n"
                "- 优先解释最早、最具体、最能导致后续连锁报错的异常；高频报错不一定是根因。\n"
                "- 不要把存档编辑、开发者模式操作、向作者反馈等建议写成可执行 action；这些只能写在 analysis 中。\n"
                "- 涉及启用/停用 Mod 或新增排序/冲突规则时，只有 package_id、动作方向和理由都明确，才允许输出 action；否则 actions 必须为空数组。\n"
                "- action 只表达应用可以直接执行的最小变更，不要在 action 里写夸大的标题或说明。\n\n"
                "analysis 部分尽量按以下结构组织：\n"
                "- 结论\n"
                "- 关键证据\n"
                "- 修复建议\n"
                "- 待验证项"
            ),
            "user_template": "{message}\n\n{diagnosis_context_block}\n",
        }, category="assistant", attachment_kinds=["diagnosis_context"]),
        "mod_general_assistant": _with_prompt_meta({
            "name": "模组通用助手",
            "description": "面向模组信息、排序、兼容、依赖与使用建议的多轮助手默认模板。",
            "system": "你是 RimCrow 内置的模组助手，负责围绕 RimWorld 模组信息进行多轮协助。\n\n你的基本原则：\n1. 优先利用当前消息、已解析附件摘要和已知事实回答，不要先入为主。\n2. 如果工具已返回足够信息，先基于现有证据收敛，不要反复检索同一问题。\n3. 明确区分“已确认事实”和“基于经验的推断”。\n4. 涉及模组时，尽量同时写出名称与 packageId；如果信息不足，就直接说明不足，不要编造。\n5. 如果用户是在比较、筛选、解释或排查模组，请优先给出清楚结论，再补简要依据。\n6. 回答始终使用 {target_lang}。\n\n如果当前会话没有足够上下文，你可以先提出最关键的下一步问题，或者在允许时调用工具补齐信息。",
            "user_template": "{message}\n\n{mod_selection_block}",
        }, category="assistant", attachment_kinds=["mod_selection"]),
    }


def get_default_assistant_definitions() -> dict[str, dict]:
    """返回系统内置助手入口定义。"""
    return {
        "assistant.log_game": _assistant_definition(
            assistant_id="assistant.log_game",
            name="游戏日志助手",
            description="面向 RimWorld 游戏日志的多轮强化诊断助手。",
            prompt_id="game_log_analysis",
            source_kinds=["logs"],
            tool_scope=[
                "get_log_context",
                "search_mods",
                "get_active_mod_list",
                "get_mod_info",
                "get_mod_rules",
                "get_mod_user_data",
                "get_group_mods",
            ],
            action_types=["MOD_STATE", "MOD_RULE"],
        ),
        "assistant.log_app": _assistant_definition(
            assistant_id="assistant.log_app",
            name="软件日志助手",
            description="面向 RimCrow 自身运行日志的多轮诊断助手。",
            prompt_id="app_log_analysis",
            source_kinds=["logs"],
            tool_scope=[],
            action_types=["TEXT_TRANSFER"],
        ),
        "assistant.mod_general": _assistant_definition(
            assistant_id="assistant.mod_general",
            name="模组助手",
            description="面向单个或多个模组信息的通用多轮助手。",
            prompt_id="mod_general_assistant",
            source_kinds=["mods", "global"],
            tool_scope=[
                "search_mods",
                "get_mod_info",
                "get_mod_rules",
                "get_mod_user_data",
                "get_group_mods",
            ],
            action_types=["MOD_STATE", "MOD_RULE"],
        ),
    }


def get_default_task_definitions() -> dict[str, dict]:
    """返回系统内置单次任务入口定义。"""
    return {
        "task.mod_alias_generation": TaskDefinition(
            id="task.mod_alias_generation",
            name="别名生成",
            description="为一个或多个模组生成通俗别名与备注。",
            prompt_id="mod_alias_generation",
            source_kinds=["mods"],
        ).model_dump(),
        "task.translation": TaskDefinition(
            id="task.translation",
            name="文本翻译",
            description="翻译业务传入的标题、说明、定义名称等文本段。",
            prompt_id="translation_general",
            source_kinds=["global"],
        ).model_dump(),
    }


def get_prompt_category_definitions() -> dict[str, dict]:
    """返回 Prompt 分类元数据与基础变量清单。"""
    return {
        "assistant": PromptCategoryDefinition(
            id="assistant",
            label="助手模板",
            description="用于多轮助手入口的提示词模板。",
            base_variables=[
                PromptVariableDefinition(key="message", label="用户输入", description="当前用户本轮输入内容。"),
                PromptVariableDefinition(key="target_lang", label="目标语言", description="当前应用界面语言对应的人类可读名称。"),
                PromptVariableDefinition(key="attachments_block", label="附件总览", description="所有附件的通用兜底摘要块。适合通用模板，不建议替代具体附件变量。"),
            ],
        ).model_dump(),
        "task": PromptCategoryDefinition(
            id="task",
            label="任务模板",
            description="用于单次任务入口的提示词模板。",
            base_variables=[
                PromptVariableDefinition(key="message", label="输入文本", description="任务入口传入的主文本。"),
                PromptVariableDefinition(key="target_lang", label="目标语言", description="当前应用界面语言对应的人类可读名称。"),
                PromptVariableDefinition(key="attachments_block", label="附件总览", description="所有附件的通用兜底摘要块。适合通用模板，不建议替代具体附件变量。"),
                PromptVariableDefinition(key="mod_alias_input_json", label="模组数据 JSON", description="模组别名任务输入的 JSON 文本。"),
                PromptVariableDefinition(key="translation_input_json", label="翻译输入 JSON", description="通用翻译任务输入的文本段 JSON。"),
                PromptVariableDefinition(key="required_segment_keys", label="必需段落键", description="翻译结果必须完整返回的 segments key 列表。"),
                PromptVariableDefinition(key="translation_context", label="翻译上下文", description="说明文本来源、用途或显示位置。"),
                PromptVariableDefinition(key="source_format", label="原文格式", description="原文格式或标记类型，例如 plain_text、steam_rich_text。"),
                PromptVariableDefinition(key="glossary_block", label="术语表", description="当前翻译可参考的术语约束。"),
            ],
        ).model_dump(),
    }
