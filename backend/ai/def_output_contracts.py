"""AI 输出协议构造器。

这里把“最终必须返回什么 JSON 结构”集中维护，避免约束散落在各个 Prompt
正文里，导致模板一改就把解析契约悄悄改坏。
"""

from __future__ import annotations

import json
from typing import Any

from backend.ai.ai_contracts import AssistantDefinition


def get_allowed_action_types(
    assistant: AssistantDefinition | None,
    action_definitions: dict[str, Any] | None = None,
) -> list[str]:
    """筛出当前助手真正允许输出的动作类型。

    只有同时出现在助手声明和动作定义表中的类型才算有效，
    这样可以避免旧配置残留引用已下线动作。
    """
    action_meta = action_definitions or {}
    return [
        str(action_type or "").strip()
        for action_type in ((assistant.action_types if assistant else []) or [])
        if str(action_type or "").strip() and action_meta.get(str(action_type or "").strip())
    ]


def build_assistant_output_contract(
    assistant: AssistantDefinition,
    action_definitions: dict[str, Any] | None = None,
) -> str:
    """构造多轮助手的最终 JSON 输出协议说明。"""
    allowed_action_types = get_allowed_action_types(assistant, action_definitions)
    action_lines: list[str] = []
    action_meta = action_definitions or {}
    for action_type in allowed_action_types:
        definition = action_meta.get(action_type) or {}
        payload_schema = definition.get("payload_schema")
        if not isinstance(payload_schema, dict):
            action_lines.append(f"- {action_type}")
            continue

        action_lines.append(f"- {action_type} 格式: {json.dumps(payload_schema.get('format') or payload_schema, ensure_ascii=False)}")
        when_text = str(payload_schema.get("when") or "").strip()
        if when_text:
            action_lines.append(f"  触发条件: {when_text}")
        examples = payload_schema.get("examples")
        if isinstance(examples, list) and examples:
            compact_examples = [item for item in examples if isinstance(item, dict)]
            if compact_examples:
                action_lines.append(f"  示例: {json.dumps(compact_examples, ensure_ascii=False)}")
        notes = payload_schema.get("notes")
        if isinstance(notes, list):
            for note in notes:
                note_text = str(note or "").strip()
                if note_text:
                    action_lines.append(f"  说明: {note_text}")

    action_rules = ""
    output_shape_line = "- JSON 结构固定为: {\"analysis\":\"面向用户的 Markdown 正文\"}。"
    if allowed_action_types:
        output_shape_line = "- JSON 结构固定为: {\"analysis\":\"面向用户的 Markdown 正文\",\"actions\":[...]}。"
        action_rules = (
            "\n动作输出约束：\n"
            "- 只有当动作类型对应的触发条件满足时才输出 action；否则 `actions` 保持空数组。\n"
            "- 可执行 action 只表达应用可以直接执行的最小变更；解释、风险、后续手工步骤都写入 `analysis`。\n"
            "- `actions` 必须是数组；每个 action 都必须包含 `type`、`variant`、`payload` 三个字段。\n"
            "- action 中不要输出 `title` / `description`；界面展示文案由应用根据动作元数据生成。\n"
            f"- 当前允许的动作类型只有: {', '.join(allowed_action_types)}\n"
            + "\n".join(action_lines)
            + "\n- `payload` 必须严格符合对应类型的字段结构，不要把 `variant` 或其它字段塞进旧位置。"
        )

    return (
        "最终输出协议：\n"
        "- 你的最终输出必须是单个 JSON 对象，不要输出 Markdown 代码块，不要在 JSON 前后补充任何解释。\n"
        f"{output_shape_line}\n"
        "- `analysis` 必须包含完整、可直接展示给用户的回答正文。\n"
        "- 如果回答正文需要包含代码块，代码块必须作为 `analysis` 字符串内容并符合 JSON 字符串转义规则；不要用外层 ```json 包裹最终对象。\n"
        f"{action_rules}\n"
        "- 不要输出除该 JSON 对象之外的任何内容。"
    )


def build_task_output_contract(task_key: str) -> str:
    """按任务类型构造单次任务的最终输出协议说明。"""
    if task_key == "task.mod_alias_generation":
        return (
            "最终输出协议：\n"
            "- 你的最终输出必须是单个 JSON 数组，不要输出 Markdown 代码块，不要补充额外解释。\n"
            "- 数组中每一项固定为: {\"package_id\":\"输入中的原始包名\",\"alias_name\":\"通俗别名\",\"notes\":\"面向新手的说明\"}。\n"
            "- `package_id` 必须与输入完全一致，不允许改写、翻译或凭空新增。\n"
            "- `alias_name` 与 `notes` 可以留空字符串，但字段本身不能缺失。\n"
            "- 不要输出数组之外的任何内容。"
        )
    if task_key == "task.translation":
        return (
            "最终输出协议：\n"
            "- 你的最终输出必须是单个 JSON 对象，不要输出 Markdown 代码块，不要补充额外解释。\n"
            "- JSON 结构固定为: {\"segments\":[{\"key\":\"输入 key\",\"text\":\"译文\"}]}。\n"
            "- `segments` 必须与输入 segments 一一对应，不能新增、删除、合并或拆分。\n"
            "- `key` 必须与输入完全一致，不允许翻译或改写。\n"
            "- `text` 是译文内容，不能为空；标题和名称也必须返回译文。\n"
            "- `text` 应保留原文换行、标签、URL、版本号、包名、文件名和 ID。\n"
            "- 不要输出该 JSON 对象之外的任何内容。"
        )
    return ""
