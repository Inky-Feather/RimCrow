"""Assistant 附件定义、解析与投影。

这个模块是附件能力的纵向聚合点：
1. 附件类型、字段投影和 prompt 变量定义
2. 前端轻量 AttachmentDraft 的校验
3. 后端权威上下文解析、字段投影和 prompt 变量提取
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from backend.ai.ai_contracts import (
    AttachmentDefinition,
    AttachmentDraft,
    AttachmentProjectionFieldDefinition,
    PromptVariableDefinition,
    ResolvedContextAttachment,
)
from backend.settings import DATA_DIR, settings
from backend.utils.logger import logger
from backend.utils.tools import normalize_package_id


def get_attachment_definitions() -> dict[str, dict]:
    """返回系统支持的附件定义。

    新增附件类型时，优先在这里补齐静态协议，然后在 `AttachmentResolver.resolve_one`
    中补充同 kind 的解析分支；调用方只消费统一的附件模块接口。
    """
    return {
        "diagnosis_context": AttachmentDefinition(
            kind="diagnosis_context",
            label="已选中日志",
            description="当前选中日志经过后端压缩后的诊断上下文。",
            allowed_owner_types=["log_viewer", "assistant"],
            required_source_keys=["owner_type", "source_type", "filename"],
            selector_modes=["summary", "all"],
            required_selector_keys=["mode"],
            prompt_variables=[
                PromptVariableDefinition(
                    key="diagnosis_context.source_type",
                    label="日志来源",
                    description="当前诊断日志的来源类型，例如 game 或 app。",
                    required_fields=["source_type"],
                ),
                PromptVariableDefinition(
                    key="diagnosis_context.filename",
                    label="日志文件名",
                    description="当前诊断目标日志文件名。",
                    required_fields=["filename"],
                ),
                PromptVariableDefinition(
                    key="diagnosis_context_block",
                    label="日志附件块",
                    description="当前日志附件的主数据块，仅包含错误摘要与少量必要统计。",
                    required_fields=["errors"],
                ),
            ],
            projection_fields=["source_type", "filename", "errors", "total_repeat_count", "selected_error_count", "truncated"],
            default_projection=["source_type", "filename", "errors", "total_repeat_count"],
            projection_options=[
                AttachmentProjectionFieldDefinition(
                    path="source_type",
                    label="日志来源类型",
                    description="当前诊断日志的来源类型，例如 game 或 app。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="filename",
                    label="日志文件名",
                    description="当前诊断目标日志文件名。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="errors",
                    label="错误摘要列表",
                    description="压缩后的错误目录项，每项包含 target_line、错误类型、消息预览、堆栈预览和关联文件。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="total_repeat_count",
                    label="总重复次数",
                    description="当前选中日志摘要覆盖的总重复次数。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="selected_error_count",
                    label="摘要条目数",
                    description="当前附件最终保留的错误摘要条目数。",
                    default_enabled=False,
                ),
                AttachmentProjectionFieldDefinition(
                    path="truncated",
                    label="是否截断",
                    description="是否因长度预算而截断了部分错误摘要。",
                    default_enabled=False,
                ),
            ],
        ).model_dump(),
        "mod_selection": AttachmentDefinition(
            kind="mod_selection",
            label="已选中模组",
            description="当前页面选中的一个或多个模组。",
            allowed_owner_types=["mod_details", "mod_list", "assistant", "task", "review_modal"],
            required_source_keys=["owner_type"],
            selector_modes=["single", "multiple", "all"],
            required_selector_keys=["mode"],
            prompt_variables=[
                PromptVariableDefinition(
                    key="mod_selection.package_ids",
                    label="已选模组包名列表",
                    description="当前模组选择包含的 packageId 列表。",
                    required_fields=["mods[].package_id"],
                ),
                PromptVariableDefinition(
                    key="mod_selection_block",
                    label="模组附件块",
                    description="当前模组附件的主数据块，仅包含选择模式与模组列表。",
                    required_fields=["mods[].package_id"],
                ),
            ],
            projection_fields=[
                "selection_mode",
                "mods[].package_id",
                "mods[].name",
                "mods[].description",
                "mods[].alias_name",
                "mods[].workshop_id",
                "mods[].author",
                "mods[].is_active",
            ],
            default_projection=[
                "mods[].package_id",
                "mods[].name",
                "mods[].description",
            ],
            projection_options=[
                AttachmentProjectionFieldDefinition(
                    path="selection_mode",
                    label="选择模式",
                    description="single / multiple / all 选择模式。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].package_id",
                    label="模组详情: 包名",
                    description="每个已选模组的 packageId。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].name",
                    label="模组详情: 名称",
                    description="每个已选模组的显示名称。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].description",
                    label="模组详情: 描述",
                    description="每个已选模组的精简描述。",
                    default_enabled=True,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].alias_name",
                    label="模组详情: 用户别名",
                    description="该模组在管理器中的用户别名。",
                    default_enabled=False,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].workshop_id",
                    label="模组详情: 工坊 ID",
                    description="Steam Workshop ID。",
                    default_enabled=False,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].author",
                    label="模组详情: 作者",
                    description="作者列表。",
                    default_enabled=False,
                ),
                AttachmentProjectionFieldDefinition(
                    path="mods[].is_active",
                    label="模组详情: 是否启用",
                    description="当前环境下该模组是否为启用状态。",
                    default_enabled=False,
                ),
            ],
        ).model_dump(),
    }


class AttachmentResolver:
    """按 kind 解析附件草稿。"""

    def __init__(self, definition_manager, llm_gateway):
        self.definition_manager = definition_manager
        self.llm = llm_gateway

    def _clean_mod_description(self, value: Any, max_length: int = 800) -> str:
        """清洗模组描述，避免把格式噪音、链接或图片引用直接带给模型。"""
        text = str(value or "")
        text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
        text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)
        text = re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<img[^>]*>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[`#>*_~\-]{2,}", " ", text)
        text = text.replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()
        if len(text) > max_length:
            text = text[:max_length].rstrip() + "..."
        return text

    def _extract_snapshot_mods(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        mods = snapshot.get("mods", []) if isinstance(snapshot, dict) else []
        if not isinstance(mods, list): return {}
        extracted: dict[str, dict[str, Any]] = {}
        for mod in mods:
            if not isinstance(mod, dict):
                continue
            package_id = normalize_package_id(mod.get("package_id"))
            if not package_id:
                continue
            extracted[package_id] = {
                "package_id": package_id,
                "name": str(mod.get("name") or "").strip(),
                "description": self._clean_mod_description(mod.get("description") or ""),
            }
        return extracted

    def resolve_many(
        self,
        payload: dict,
        *,
        active_context=None,
        reader=None,
        prompt_id: str | None = None,
    ) -> list[ResolvedContextAttachment]:
        """批量解析前端附件草稿，尽量跳过坏数据而不是整批失败。"""
        attachments: list[ResolvedContextAttachment] = []
        for raw_attachment in payload.get("attachments", []) or []:
            try:
                draft = AttachmentDraft.model_validate(raw_attachment)
            except Exception:
                continue
            try:
                attachments.append(
                    self.resolve_one(
                        draft,
                        active_context=active_context,
                        reader=reader,
                        prompt_id=prompt_id,
                    )
                )
            except Exception as exc:
                logger.warning(f"[AI附件] 跳过无效附件 kind={draft.kind!r}: {exc}")
        return attachments

    def build_prompt_block(self, attachments: list[ResolvedContextAttachment]) -> str:
        """把附件集合压成通用提示词块，供通用 Prompt 兜底引用。"""
        if not attachments:
            return ""
        blocks: list[str] = []
        for attachment in attachments:
            facts = attachment.facts if isinstance(attachment.facts, dict) else {}
            compact_facts = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
            if compact_facts == "{}":
                compact_facts = ""
            lines = [f"[附件]{attachment.title or attachment.type}"]
            if attachment.summary:
                lines.append(f"摘要: {attachment.summary}")
            if compact_facts:
                lines.append(f"数据: {compact_facts}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def extract_prompt_variables(self, attachments: list[ResolvedContextAttachment]) -> dict[str, Any]:
        """从附件中提取 Prompt 可直接引用的变量映射。"""
        extracted: dict[str, Any] = {}
        grouped_blocks: dict[str, list[dict[str, Any]]] = {}
        for attachment in attachments or []:
            facts = dict(attachment.facts or {}) if isinstance(attachment.facts, dict) else {}
            grouped_blocks.setdefault(str(attachment.type or "").strip(), []).append({
                "title": str(attachment.title or "").strip(),
                "summary": str(attachment.summary or "").strip(),
                "facts": facts,
            })

            if attachment.type == "diagnosis_context":
                source_type = str(facts.get("source_type") or "").strip()
                filename = str(facts.get("filename") or "").strip()
                if source_type:
                    extracted["diagnosis_context.source_type"] = source_type
                if filename:
                    extracted["diagnosis_context.filename"] = filename
            elif attachment.type == "mod_selection":
                extracted["mod_selection.package_ids"] = json.dumps(
                    self._extract_mod_package_ids(facts),
                    ensure_ascii=False,
                )

        if grouped_blocks.get("diagnosis_context"):
            extracted["diagnosis_context_block"] = json.dumps(grouped_blocks["diagnosis_context"], ensure_ascii=False)
        if grouped_blocks.get("mod_selection"):
            extracted["mod_selection_block"] = json.dumps(grouped_blocks["mod_selection"], ensure_ascii=False)

        return extracted

    def resolve_one(
        self,
        draft: AttachmentDraft,
        *,
        active_context=None,
        reader=None,
        prompt_id: str | None = None,
    ) -> ResolvedContextAttachment:
        """把单个附件草稿补齐成可投喂模型的权威附件对象。"""
        is_valid, error_message = self._validate_draft(draft)
        if not is_valid:
            raise ValueError(f"invalid attachment draft ({draft.kind}): {error_message}")

        kind = str(draft.kind or "").strip()
        source = dict(draft.source or {})
        selector = dict(draft.selector or {})
        snapshot = dict(draft.snapshot or {})
        source_type = str(source.get("source_type") or "").strip()
        filename = str(source.get("filename") or "").strip()
        owner_type = str(source.get("owner_type") or "").strip()

        facts: dict[str, Any] = {}
        title = kind or "attachment"
        summary = str(snapshot.get("summary") or kind)

        if kind == "diagnosis_context":
            title = "已选中日志"
            selected_lines = selector.get("values", [])
            try:
                if reader and filename:
                    from backend.managers.mgr_game_logs import LogCondenser

                    if source_type == "game":
                        filepath = os.path.join(active_context.user_data_path, filename) if active_context else ""
                    else:
                        filepath = os.path.join(DATA_DIR, "logs", filename)
                    if filepath and os.path.exists(filepath):
                        raw_logs = []
                        mode = str(selector.get("mode") or "").strip()
                        if mode == "all" and hasattr(reader, "get_all_blocks"):
                            raw_logs = reader.get_all_blocks(filepath, full_scan=True) or []
                        elif isinstance(selected_lines, list) and selected_lines and hasattr(reader, "get_raw_logs_by_lines"):
                            raw_logs = reader.get_raw_logs_by_lines(filepath, selected_lines) or []

                        if raw_logs:
                            condensed = LogCondenser.condense_for_ai(
                                raw_logs,
                                token_limit=settings.config.ai.max_tokens,
                                char_budget_ratio=0.65,
                                stack_preview_lines=2,
                            )
                            if isinstance(condensed, dict):
                                facts = {
                                    "source_type": source_type,
                                    "filename": filename,
                                    "errors": list(condensed.get("errors", []) or []),
                                    "total_repeat_count": int(condensed.get("total_repeat_count", 0) or 0),
                                    "selected_error_count": int(condensed.get("selected_error_count", 0) or 0),
                                    "truncated": bool(condensed.get("truncated", False)),
                                }
                                summary = str(
                                    condensed.get("summary")
                                    or snapshot.get("summary")
                                    or f"已选 {len(facts.get('errors', []))} 条错误摘要"
                                )
            except Exception as exc:
                logger.warning(f"[AI附件] 解析诊断上下文失败 owner={owner_type!r} filename={filename!r}: {exc}")

        elif kind == "mod_selection":
            title = "已选中模组"
            mode = str(selector.get("mode") or "").strip() or "single"
            package_ids = selector.get("values", [])
            if not isinstance(package_ids, list):
                package_ids = []
            normalized_package_ids: list[str] = []
            seen_package_ids: set[str] = set()
            for raw_package_id in package_ids:
                package_id = str(raw_package_id or "").strip()
                if not package_id or package_id in seen_package_ids:
                    continue
                seen_package_ids.add(package_id)
                normalized_package_ids.append(package_id)
            if mode == "single" and not normalized_package_ids:
                single_package_id = str(source.get("package_id") or "").strip()
                if single_package_id:
                    normalized_package_ids.append(single_package_id)

            visible_mods: dict[str, dict[str, Any]] = self._extract_snapshot_mods(snapshot)
            if active_context:
                try:
                    from backend.database.dao import ModDAO

                    for mod in ModDAO.get_profile_mods(active_context) or []:
                        package_id = normalize_package_id(mod.get("package_id"))
                        if package_id:
                            visible_mods[package_id] = mod
                except Exception as exc:
                    logger.warning(f"[AI附件] 读取模组选择上下文失败: {exc}")

            selected_mods: list[dict[str, Any]] = []
            for package_id in normalized_package_ids:
                mod = dict(visible_mods.get(package_id) or {})
                mod_package_id = normalize_package_id(mod.get("package_id")) or package_id
                mod_name = str(mod.get("name") or source.get("name") or "").strip()
                mod_description = self._clean_mod_description(mod.get("description") or source.get("description") or "")
                selected_mods.append({
                    "package_id": mod_package_id,
                    "name": mod_name,
                    "description": mod_description,
                })

            facts = {
                "selection_mode": mode,
                "mods": selected_mods,
            }
            summary = str(
                snapshot.get("summary")
                or (str(selected_mods[0].get("name") or "").strip() if mode == "single" and selected_mods else "")
                or (f"已选 {len(normalized_package_ids)} 个模组" if normalized_package_ids else "模组选择")
            )

        projection_fields = self.definition_manager.get_attachment_projection_fields(
            kind,
            prompt_id=prompt_id,
            options=dict(draft.options or {}),
        )
        attachment_definition = self.definition_manager.attachment_definitions.get(kind) or {}
        if not projection_fields:
            projection_fields = list(
                attachment_definition.get("default_projection")
                or attachment_definition.get("projection_fields")
                or []
            )
        projected_facts = self._project_attachment_facts(facts, projection_fields)

        return ResolvedContextAttachment(
            type=kind,
            title=title,
            summary=summary,
            facts=projected_facts,
            token_estimate=self._estimate_text_tokens(
                json.dumps(projected_facts, ensure_ascii=False),
                settings.config.ai.model,
            ),
        )

    def _validate_draft(self, draft: AttachmentDraft) -> tuple[bool, str]:
        definition = self.definition_manager.attachment_definitions.get(draft.kind)
        if not definition: return False, f"unknown kind: {draft.kind}"

        source = dict(draft.source or {})
        selector = dict(draft.selector or {})
        owner_type = str(source.get("owner_type") or "").strip()
        selector_mode = str(selector.get("mode") or "").strip()

        allowed_owner_types = [
            str(item or "").strip()
            for item in definition.get("allowed_owner_types", []) or []
            if str(item or "").strip()
        ]
        if allowed_owner_types and owner_type not in allowed_owner_types:
            return False, f"owner_type not allowed: {owner_type or '<empty>'}"

        for key in definition.get("required_source_keys", []) or []:
            if source.get(key) in (None, "", []):
                return False, f"missing source key: {key}"

        if selector_mode not in set(definition.get("selector_modes", []) or []):
            return False, f"selector mode not allowed: {selector_mode or '<empty>'}"

        for key in definition.get("required_selector_keys", []) or []:
            if selector.get(key) in (None, "", []):
                return False, f"missing selector key: {key}"

        return True, ""

    def _extract_mod_package_ids(self, facts: dict[str, Any]) -> list[str]:
        mods = facts.get("mods", [])
        if not isinstance(mods, list): return []
        package_ids: list[str] = []
        seen: set[str] = set()
        for mod in mods:
            if not isinstance(mod, dict):
                continue
            package_id = str(mod.get("package_id") or "").strip()
            if not package_id or package_id in seen:
                continue
            seen.add(package_id)
            package_ids.append(package_id)
        return package_ids

    def _split_projection_path(self, path: str) -> list[str]:
        return [part.strip() for part in str(path or "").split(".") if str(part or "").strip()]

    def _strip_list_token(self, part: str) -> str:
        return str(part or "").replace("[]", "").strip()

    def _read_projection_value(self, data: Any, path: str) -> tuple[bool, Any]:
        current = data
        for part in self._split_projection_path(path):
            normalized_part = self._strip_list_token(part)
            if isinstance(current, list):
                next_list = []
                for item in current:
                    if isinstance(item, dict) and normalized_part in item:
                        next_list.append(item.get(normalized_part))
                current = next_list
                continue
            if isinstance(current, dict) and normalized_part in current:
                current = current.get(normalized_part)
                continue
            return False, None
        return True, current

    def _write_projection_value(self, target: dict[str, Any], path: str, value: Any) -> None:
        parts = self._split_projection_path(path)
        if not parts: return
        current = target
        for part in parts[:-1]:
            normalized_part = self._strip_list_token(part)
            next_value = current.get(normalized_part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[normalized_part] = next_value
            current = next_value
        current[self._strip_list_token(parts[-1])] = value

    def _merge_projected_values(self, current: Any, incoming: Any) -> Any:
        if isinstance(current, dict) and isinstance(incoming, dict):
            merged = dict(current)
            for key, value in incoming.items():
                merged[key] = self._merge_projected_values(merged.get(key), value)
            return merged

        if isinstance(current, list) and isinstance(incoming, list):
            merged_items: list[Any] = []
            max_len = max(len(current), len(incoming))
            for index in range(max_len):
                current_item = current[index] if index < len(current) else None
                incoming_item = incoming[index] if index < len(incoming) else None
                if current_item is None:
                    merged_items.append(incoming_item)
                elif incoming_item is None:
                    merged_items.append(current_item)
                else:
                    merged_items.append(self._merge_projected_values(current_item, incoming_item))
            return merged_items

        return incoming if incoming is not None else current

    def _build_projected_fragment(self, parts: list[str], value: Any) -> Any:
        if not parts: return value
        head = self._strip_list_token(parts[0])
        if "[]" in str(parts[0]) and isinstance(value, list):
            return {
                head: [
                    self._build_projected_fragment(parts[1:], item)
                    for item in value
                ]
            }
        return {head: self._build_projected_fragment(parts[1:], value)}

    def _project_attachment_facts(self, facts: dict[str, Any], projection_fields: list[str] | None) -> dict[str, Any]:
        normalized_fields = [
            str(field or "").strip()
            for field in (projection_fields or [])
            if str(field or "").strip()
        ]
        if not normalized_fields: return dict(facts or {})

        projected: dict[str, Any] = {}
        for field in normalized_fields:
            exists, value = self._read_projection_value(facts, field)
            if not exists:
                continue
            if "[]" in field:
                fragment = self._build_projected_fragment(self._split_projection_path(field), value)
                projected = self._merge_projected_values(projected, fragment)
                continue
            self._write_projection_value(projected, field, value)
        return projected

    def _estimate_text_tokens(self, text: str, model_name: str) -> int:
        return self.llm.estimate_text_tokens(text, model_name)
