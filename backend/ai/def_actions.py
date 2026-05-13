"""AI action definitions and normalization helpers."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from backend.ai.ai_contracts import (
    AIAction,
    ActionDefinition,
    ActionVariantDefinition,
)
from backend.utils.logger import logger


def get_action_definitions() -> dict[str, dict]:
    """返回系统支持的可执行动作定义。

    新增 action 时，先在这里声明 payload、触发条件和展示元数据；
    如果它需要真正执行，再在前端 action executor 中补一个执行 adapter。
    """
    return {
        "MOD_STATE": ActionDefinition(
            type="MOD_STATE",
            label="模组启用状态",
            description="调整一个或多个模组的启用状态。",
            execute_label="应用模组状态调整",
            unsupported_message="当前前端暂不支持执行这种模组状态动作。",
            execution_failed_message="应用模组状态动作失败：{error}",
            render_config={
                "split_payload_list_key": "mod_ids",
                "subjects": [
                    {"payload_key": "mod_ids", "entity_type": "mod", "tone": "primary"},
                ],
            },
            payload_schema={
                "format": {
                    "type": "MOD_STATE",
                    "variant": "enable or disable",
                    "payload": {"mod_ids": ["package.id"]},
                },
                "when": "当一个或多个 package_id 和启用/停用方向已经明确时输出；无需额外目标对象。",
                "examples": [
                    {"type": "MOD_STATE", "variant": "enable", "payload": {"mod_ids": ["zal.darknet", "zal.cosmos"]}},
                    {"type": "MOD_STATE", "variant": "disable", "payload": {"mod_ids": ["bad.mod.package"]}},
                ],
                "notes": [
                    "enable 表示把这些模组加入启用列表。",
                    "disable 表示把这些模组从启用列表移除。",
                    "不要把存档清理、开发者模式操作、反馈作者等不可直接执行步骤写成 action。",
                ],
            },
            variants={
                "enable": ActionVariantDefinition(
                    label="模组启用状态",
                    title="启用模组",
                    description="将指定模组加入启用列表。",
                    preview_template="建议将 {mod_ids_display_joined} 调整为启用状态。",
                    render_config={
                        "card_tone": "success",
                        "subjects": [
                            {"payload_key": "mod_ids", "entity_type": "mod", "tone": "success"},
                        ],
                    },
                    execute_label="启用这个模组",
                    missing_payload_message="这条启用动作缺少有效的 mod_ids，已跳过。",
                    success_message="已启用: {mod_ids_display_csv}",
                ),
                "disable": ActionVariantDefinition(
                    label="模组启用状态",
                    title="停用模组",
                    description="将指定模组从启用列表移除。",
                    preview_template="建议将 {mod_ids_display_joined} 调整为停用状态。",
                    render_config={
                        "card_tone": "warning",
                        "subjects": [
                            {"payload_key": "mod_ids", "entity_type": "mod", "tone": "warning"},
                        ],
                    },
                    execute_label="停用这个模组",
                    missing_payload_message="这条停用动作缺少有效的 mod_ids，已跳过。",
                    success_message="已停用: {mod_ids_display_csv}",
                ),
            },
        ).model_dump(),
        "MOD_RULE": ActionDefinition(
            type="MOD_RULE",
            label="模组规则",
            description="添加一条加载顺序或兼容性规则。",
            execute_label="应用模组规则",
            unsupported_message="当前前端暂不支持执行这种模组规则动作。",
            execution_failed_message="应用模组规则失败：{error}",
            render_config={
                "subjects": [
                    {"payload_key": "mod_id", "entity_type": "mod", "tone": "special"},
                    {"payload_key": "target_id", "entity_type": "mod", "tone": "primary"},
                ],
            },
            payload_schema={
                "format": {
                    "type": "MOD_RULE",
                    "variant": "loadAfter or loadBefore or incompatibleWith",
                    "payload": {"mod_id": "package.a", "target_id": "package.b"},
                },
                "when": "仅当两个 package_id 和规则方向都明确时输出。",
                "examples": [
                    {"type": "MOD_RULE", "variant": "loadAfter", "payload": {"mod_id": "package.a", "target_id": "package.b"}},
                    {"type": "MOD_RULE", "variant": "loadBefore", "payload": {"mod_id": "package.a", "target_id": "package.b"}},
                    {"type": "MOD_RULE", "variant": "incompatibleWith", "payload": {"mod_id": "package.a", "target_id": "package.b"}},
                ],
                "notes": [
                    "loadAfter 表示 mod_id 必须排在 target_id 后面，即 target_id 是 mod_id 的前置。",
                    "loadBefore 表示 mod_id 必须排在 target_id 前面，即 target_id 是 mod_id 的后置。",
                    "incompatibleWith 表示 mod_id 与 target_id 不应同时启用。",
                    "如果只能判断可能冲突但不知道准确规则方向，请不要输出 MOD_RULE，改写入 analysis。",
                ],
            },
            variants={
                "loadAfter": ActionVariantDefinition(
                    label="模组规则",
                    title="前置规则",
                    description="建议建立一条前置规则。",
                    preview_template="建议将 {target_id_display} 设置为 {mod_id_display} 的前置模组。",
                    render_config={
                        "card_tone": "warn",
                        "subjects": [
                            {"payload_key": "target_id", "entity_type": "mod", "tone": "warn"},
                            {"payload_key": "mod_id", "entity_type": "mod", "tone": "special"},
                        ],
                    },
                    execute_label="应用前置规则",
                    missing_payload_message="这条规则动作缺少必要字段，已跳过。",
                    confirm_title="确认应用前置规则",
                    confirm_message="{target_id_display} 将被设置为 {mod_id_display} 的前置模组",
                    confirm_confirm_text="应用规则",
                    post_success_title="规则已应用",
                    post_success_message="是否立即重新执行自动排序以使规则生效？",
                    post_success_confirm_text="立即排序",
                ),
                "loadBefore": ActionVariantDefinition(
                    label="模组规则",
                    title="后置规则",
                    description="建议建立一条后置规则。",
                    preview_template="建议将 {target_id_display} 设置为 {mod_id_display} 的后置模组。",
                    render_config={
                        "card_tone": "primary",
                        "subjects": [
                            {"payload_key": "target_id", "entity_type": "mod", "tone": "primary"},
                            {"payload_key": "mod_id", "entity_type": "mod", "tone": "special"},
                        ],
                    },
                    execute_label="应用后置规则",
                    missing_payload_message="这条规则动作缺少必要字段，已跳过。",
                    confirm_title="确认应用后置规则",
                    confirm_message="{target_id_display} 将被设置为 {mod_id_display} 的后置模组",
                    confirm_confirm_text="应用规则",
                    post_success_title="规则已应用",
                    post_success_message="是否立即重新执行自动排序以使规则生效？",
                    post_success_confirm_text="立即排序",
                ),
                "incompatibleWith": ActionVariantDefinition(
                    label="模组规则",
                    title="冲突规则",
                    description="建议建立一条冲突规则。",
                    preview_template="建议将 {target_id_display} 设置为 {mod_id_display} 的冲突模组。",
                    render_config={
                        "card_tone": "danger",
                        "subjects": [
                            {"payload_key": "target_id", "entity_type": "mod", "tone": "danger"},
                            {"payload_key": "mod_id", "entity_type": "mod", "tone": "special"},
                        ],
                    },
                    execute_label="应用冲突规则",
                    missing_payload_message="这条规则动作缺少必要字段，已跳过。",
                    confirm_title="确认应用冲突规则",
                    confirm_message="{target_id_display} 将被设置为 {mod_id_display} 的冲突模组",
                    confirm_confirm_text="应用规则",
                    post_success_title="规则已应用",
                    post_success_message="是否立即重新执行自动排序以使规则生效？",
                    post_success_confirm_text="立即排序",
                ),
            },
        ).model_dump(),
        "TEXT_TRANSFER": ActionDefinition(
            type="TEXT_TRANSFER",
            label="文本转移",
            description="把一段文本交给前端进行复制或转交。",
            execute_label="复制文本",
            unsupported_message="当前前端暂不支持执行这种文本动作。",
            execution_failed_message="复制文本失败：{error}",
            payload_schema={
                "type": "TEXT_TRANSFER",
                "variant": "copy_report",
                "payload": {"text": "可直接复制的反馈正文"},
            },
            variants={
                "copy_report": ActionVariantDefinition(
                    label="文本转移",
                    title="复制反馈文本",
                    description="复制一段可直接反馈给作者或社区的问题说明。",
                    preview_template="{text}",
                    execute_label="复制到剪贴板",
                    missing_payload_message="这条文本动作缺少可复制内容，已跳过。",
                    success_message="文本已复制到剪贴板。",
                ),
            },
        ).model_dump(),
        "SETTING_UPDATE": ActionDefinition(
            type="SETTING_UPDATE",
            label="设置更新",
            description="修改一个已注册的设置项。",
            execute_label="应用设置修改",
            unsupported_message="当前前端暂不支持执行这种设置动作。",
            execution_failed_message="应用设置修改失败：{error}",
            payload_schema={
                "type": "SETTING_UPDATE",
                "variant": "set_value",
                "payload": {"setting_key": "ui.show_ai_assistant", "value": False},
            },
            execution_config={
                "allowed_setting_keys": [
                    "enable_tool_mods",
                    "debug_mode",
                    "language",
                ],
            },
            variants={
                "set_value": ActionVariantDefinition(
                    label="设置更新",
                    title="修改设置项",
                    description="建议修改一个已注册且允许 AI 触发的设置项。",
                    preview_template="{setting_key} => {value_json}",
                    execute_label="应用设置修改",
                    missing_payload_message="这条设置动作缺少 setting_key，已跳过。",
                    blocked_message="不允许通过 AI 修改该设置项: {setting_key}",
                    success_message="已更新设置: {setting_key}",
                ),
            },
        ).model_dump(),
    }


def create_action_normalization_debug() -> dict[str, Any]:
    """创建动作归一化诊断对象。

    这里单独抽成工厂函数，方便不同入口复用同一份统计字段，
    也避免后续加诊断项时到处补默认值。
    """
    return {
        "input_count": 0,
        "normalized_count": 0,
        "input_type": "list",
        "normalized_breakdown": {},
        "dropped_counts": {},
    }


def _increment_action_debug_counter(counters: dict[str, int], key: str, amount: int = 1) -> None:
    counter_key = str(key or "").strip()
    if not counter_key: return
    counters[counter_key] = int(counters.get(counter_key, 0) or 0) + int(amount or 0)


def normalize_ai_actions(
    raw_actions: Any,
    *,
    action_definitions: dict[str, Any] | None = None,
    allowed_action_types: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """校验、授权、去重并补齐 AI 动作。"""
    diagnostics = create_action_normalization_debug()
    if not isinstance(raw_actions, list):
        diagnostics["input_type"] = type(raw_actions).__name__ if raw_actions is not None else "null"
        return [], diagnostics

    diagnostics["input_count"] = len(raw_actions)
    normalized_actions: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    action_meta = action_definitions or {}
    allowed_type_set = {
        str(action_type or "").strip()
        for action_type in (allowed_action_types or [])
        if str(action_type or "").strip()
    }
    for index, raw_action in enumerate(raw_actions):
        if not isinstance(raw_action, dict):
            _increment_action_debug_counter(diagnostics["dropped_counts"], "non_object")
            continue
        try:
            normalized_action = AIAction.model_validate(raw_action).model_dump()
            action_type = str(normalized_action.get("type") or "").strip()
            if allowed_type_set and action_type not in allowed_type_set:
                logger.warning(f"[AI动作解析] 已跳过未授权 action type={action_type or '<empty>'} index={index}")
                _increment_action_debug_counter(diagnostics["dropped_counts"], "unauthorized_type")
                continue
            definition = action_meta.get(action_type) or {}
            variant_key = str(normalized_action.get("variant") or "").strip()
            variant_definition = (
                (definition.get("variants") or {}).get(variant_key, {})
                if isinstance(definition.get("variants"), dict)
                else {}
            )
            metadata_title = str(
                variant_definition.get("title")
                or definition.get("label")
                or ""
            ).strip()
            metadata_description = str(
                variant_definition.get("description")
                or definition.get("description")
                or ""
            ).strip()
            normalized_action["title"] = str(
                metadata_title
                or normalized_action.get("title")
                or ""
            ).strip()
            normalized_action["description"] = str(
                metadata_description
                or normalized_action.get("description")
                or ""
            ).strip()
            signature = json.dumps({
                "type": normalized_action.get("type"),
                "variant": normalized_action.get("variant"),
                "payload": normalized_action.get("payload", {}),
            }, ensure_ascii=False, sort_keys=True)
            if signature in seen_signatures:
                logger.warning(f"[AI动作解析] 已去重重复 action index={index}")
                _increment_action_debug_counter(diagnostics["dropped_counts"], "duplicate")
                continue
            seen_signatures.add(signature)
            normalized_actions.append(normalized_action)
        except ValidationError as exc:
            logger.warning(f"[AI动作解析] 已跳过非法 action index={index}: {exc}")
            _increment_action_debug_counter(diagnostics["dropped_counts"], "validation_failed")

    enabled_mods: set[str] = set()
    disabled_mods: set[str] = set()
    for action in normalized_actions:
        payload = action.get("payload", {}) if isinstance(action, dict) else {}
        mod_ids = payload.get("mod_ids", []) if isinstance(payload, dict) else []
        if action.get("type") == "MOD_STATE" and action.get("variant") == "enable":
            enabled_mods.update(str(mod_id).strip().lower() for mod_id in mod_ids)
        elif action.get("type") == "MOD_STATE" and action.get("variant") == "disable":
            disabled_mods.update(str(mod_id).strip().lower() for mod_id in mod_ids)

    conflicted_mods = enabled_mods & disabled_mods
    if conflicted_mods:
        logger.warning(f"[AI动作解析] 已丢弃互相冲突的启停动作 mods={sorted(conflicted_mods)}")
        filtered_actions: list[dict[str, Any]] = []
        conflict_drop_count = 0
        for action in normalized_actions:
            payload = action.get("payload", {}) if isinstance(action, dict) else {}
            mod_ids = payload.get("mod_ids", []) if isinstance(payload, dict) else []
            normalized_mod_ids = {str(mod_id).strip().lower() for mod_id in mod_ids}
            if action.get("type") == "MOD_STATE" and normalized_mod_ids & conflicted_mods:
                conflict_drop_count += 1
                continue
            filtered_actions.append(action)
        normalized_actions = filtered_actions
        _increment_action_debug_counter(diagnostics["dropped_counts"], "conflicting_mod_state", conflict_drop_count)

    normalized_breakdown: dict[str, int] = {}
    for action in normalized_actions:
        breakdown_key = f"{action.get('type')}.{action.get('variant')}"
        _increment_action_debug_counter(normalized_breakdown, breakdown_key)
    diagnostics["normalized_breakdown"] = normalized_breakdown
    diagnostics["normalized_count"] = len(normalized_actions)

    return normalized_actions, diagnostics
