"""AI 定义管理模块。

职责边界：
1. 默认 Prompt / Assistant / Task 定义全部由代码维护
2. `ai_definitions.json` 保存用户可编辑的 AI 定义数据：
   - 自定义 Prompt
   - 系统 Assistant 的绑定/工具覆写
   - 系统 Task 的 Prompt 绑定覆写
3. 运行期数据由“代码默认定义 + 定义文件中的用户覆写”合成
"""

import json
import os
import re
import threading
import unicodedata
from copy import deepcopy
from typing import Any

from backend.ai.ai_contracts import (
    AssistantDefinition,
    TaskDefinition,
)
from backend.ai.def_entries import (
    get_default_ai_prompts,
    get_default_assistant_definitions,
    get_default_task_definitions,
    get_prompt_category_definitions,
)
from backend.ai.def_actions import get_action_definitions
from backend.ai.def_attachments import get_attachment_definitions
from backend.utils.tools import normalize_string_list, normalize_text
from backend.utils.logger import logger


_PROMPT_VARIABLE_PATTERN = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}|\{([A-Za-z0-9_.]+)\}")


class AIDefinitionManager:
    """统一负责 AI 定义文件、默认 Prompt 与运行时助手/任务定义。"""

    STORE_VERSION = 1

    def __init__(self, definition_file: str):
        self.definition_file = definition_file
        self._save_lock = threading.Lock()
        self.prompts: dict[str, dict] = {}
        self.custom_prompts: dict[str, dict] = {}
        self.assistant_overrides: dict[str, dict] = {}
        self.task_overrides: dict[str, dict] = {}
        self.assistants: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self._default_prompts = get_default_ai_prompts()
        self._default_assistants = get_default_assistant_definitions()
        self._default_tasks = get_default_task_definitions()
        self.prompt_categories = get_prompt_category_definitions()
        self.attachment_definitions = get_attachment_definitions()
        self.action_definitions = get_action_definitions()
        self._default_prompt_ids = set(self._default_prompts)
        self._default_assistant_ids = set(self._default_assistants)
        self._default_task_ids = set(self._default_tasks)

        os.makedirs(os.path.dirname(self.definition_file), exist_ok=True)
        self.ensure_default_files()
        self.reload()

    def get_prompt_defaults(self) -> dict:
        """返回系统 Prompt 默认定义的深拷贝。

        调用方经常会在返回结果上临时打补丁；这里始终返回副本并补上
        `is_system=True`，避免把运行时标记反向污染到内部缓存。
        """
        defaults = deepcopy(self._default_prompts)
        for prompt_data in defaults.values():
            prompt_data["is_system"] = True
        return defaults

    def get_assistant_defaults(self) -> dict:
        """返回系统助手默认定义的深拷贝。"""
        defaults = deepcopy(self._default_assistants)
        for assistant_data in defaults.values():
            assistant_data["is_system"] = True
        return defaults

    def get_task_defaults(self) -> dict:
        """返回系统任务默认定义的深拷贝。"""
        defaults = deepcopy(self._default_tasks)
        for task_data in defaults.values():
            task_data["is_system"] = True
        return defaults

    def _extract_prompt_variables(self, text: str) -> set[str]:
        variables: set[str] = set()
        for match in _PROMPT_VARIABLE_PATTERN.finditer(str(text or "")):
            variable = match.group(1) or match.group(2) or ""
            variable = variable.strip()
            if variable:
                variables.add(variable)
        return variables

    def _normalize_attachment_kinds(self, attachment_kinds: list[str] | tuple[str, ...] | None) -> list[str]:
        return [key for key in normalize_string_list(attachment_kinds) if key in self.attachment_definitions]

    def _normalize_projection_fields(self, projection_fields: Any) -> list[str]:
        if isinstance(projection_fields, str):
            return normalize_string_list([projection_fields])
        return normalize_string_list(projection_fields or [])

    def _normalize_attachment_projection_overrides(
        self,
        override_map: dict[str, Any] | None,
        attachment_kinds: list[str] | None = None,
    ) -> dict[str, dict[str, list[str]]]:
        normalized: dict[str, dict[str, list[str]]] = {}
        allowed_kinds = set(self._normalize_attachment_kinds(attachment_kinds or []))
        raw_map = override_map if isinstance(override_map, dict) else {}
        for kind, raw_options in raw_map.items():
            normalized_kind = normalize_text(kind)
            if not normalized_kind or normalized_kind not in allowed_kinds:
                continue
            attachment_data = self.attachment_definitions.get(normalized_kind) or {}
            known_fields = set(self._normalize_projection_fields(
                attachment_data.get("projection_fields") or attachment_data.get("default_projection") or []
            ))
            known_fields.update(
                str(field.get("path") or "").strip()
                for field in (attachment_data.get("projection_options") or [])
                if str(field.get("path") or "").strip()
            )
            option_map = raw_options if isinstance(raw_options, dict) else {}
            include_fields = [
                field for field in self._normalize_projection_fields(option_map.get("include_fields"))
                if not known_fields or field in known_fields
            ]
            exclude_fields = [
                field for field in self._normalize_projection_fields(option_map.get("exclude_fields"))
                if not known_fields or field in known_fields
            ]
            if include_fields or exclude_fields:
                normalized[normalized_kind] = {
                    "include_fields": include_fields,
                    "exclude_fields": exclude_fields,
                }
        return normalized

    def _get_prompt_variable_whitelist(self, category: str, attachment_kinds: list[str] | None = None) -> set[str]:
        allowed: set[str] = set()
        category_data = self.prompt_categories.get(category) or {}
        for variable in category_data.get("base_variables", []) or []:
            key = str(variable.get("key") or "").strip()
            if key:
                allowed.add(key)

        for attachment_kind in attachment_kinds or []:
            attachment_data = self.attachment_definitions.get(str(attachment_kind or "").strip()) or {}
            for variable in attachment_data.get("prompt_variables", []) or []:
                key = str(variable.get("key") or "").strip()
                if key:
                    allowed.add(key)
        return allowed

    def get_attachment_projection_fields( self, attachment_kind: str, *, prompt_id: str | None = None, options: dict[str, Any] | None = None ) -> list[str]:
        """解析附件最终需要暴露给模型的字段集合。

        字段来源有三层优先级：
        1. 调用方显式传入的 include/exclude
        2. Prompt 绑定的附件投影覆写
        3. 附件定义自己的默认投影

        同时还会把 Prompt 实际引用到的变量所依赖字段补回来，避免用户在
        编辑器里误删字段后把模板渲染成空值。
        """
        attachment_data = self.attachment_definitions.get(str(attachment_kind or "").strip()) or {}
        if not attachment_data: return []

        option_map = options if isinstance(options, dict) else {}
        include_fields = self._normalize_projection_fields(option_map.get("include_fields"))
        exclude_fields = set(self._normalize_projection_fields(option_map.get("exclude_fields")))
        default_projection = self._normalize_projection_fields(
            attachment_data.get("default_projection")
            or attachment_data.get("projection_fields")
            or []
        )

        required_fields: list[str] = []
        if prompt_id:
            prompt_data = self.prompts.get(str(prompt_id or "").strip()) or {}
            prompt_projection_overrides = self._normalize_attachment_projection_overrides(
                prompt_data.get("attachment_projection_overrides", {}),
                prompt_data.get("attachment_kinds", []),
            )
            prompt_override_options = prompt_projection_overrides.get(str(attachment_kind or "").strip()) or {}
            if not include_fields:
                include_fields = self._normalize_projection_fields(prompt_override_options.get("include_fields"))
            if not exclude_fields:
                exclude_fields = set(self._normalize_projection_fields(prompt_override_options.get("exclude_fields")))
            used_variables = self._extract_prompt_variables(prompt_data.get("system", ""))
            used_variables.update(self._extract_prompt_variables(prompt_data.get("user_template", "")))
            for variable in attachment_data.get("prompt_variables", []) or []:
                key = str(variable.get("key") or "").strip()
                if not key or key not in used_variables:
                    continue
                required_fields.extend(variable.get("required_fields") or [])

        ordered_fields: list[str] = []
        seen: set[str] = set()
        required_field_set = set(self._normalize_projection_fields(required_fields))
        base_fields = include_fields or default_projection
        for field in [*base_fields, *required_field_set]:
            if not field or field in seen:
                continue
            if field in exclude_fields and field not in required_field_set:
                continue
            seen.add(field)
            ordered_fields.append(field)
        return ordered_fields

    def _validate_prompt_template(self, prompt_id: str, prompt_data: dict) -> None:
        category = str(prompt_data.get("category") or "").strip()
        if category not in self.prompt_categories:
            raise ValueError(f"Prompt {prompt_id} category is invalid: {category or '<empty>'}")

        attachment_kinds = self._normalize_attachment_kinds(prompt_data.get("attachment_kinds", []))
        allowed_variables = self._get_prompt_variable_whitelist(category, attachment_kinds)
        used_variables = self._extract_prompt_variables(prompt_data.get("system", ""))
        used_variables.update(self._extract_prompt_variables(prompt_data.get("user_template", "")))
        unknown_variables = sorted(var for var in used_variables if var not in allowed_variables)
        if unknown_variables:
            raise ValueError(
                f"Prompt {prompt_id} contains unsupported variables: {', '.join(unknown_variables)}"
            )

    def _merge_runtime_prompts(self) -> dict:
        merged = self.get_prompt_defaults()
        merged.update(deepcopy(self.custom_prompts))
        return merged

    def _assert_prompt_binding(self, owner_id: str, prompt_id: str, expected_category: str) -> None:
        normalized_prompt_id = str(prompt_id or "").strip()
        prompt_data = self.prompts.get(normalized_prompt_id)
        if not prompt_data:
            raise ValueError(f"{owner_id} references unknown prompt: {normalized_prompt_id or '<empty>'}")
        actual_category = str(prompt_data.get("category") or "").strip()
        if actual_category != expected_category:
            raise ValueError(
                f"{owner_id} must bind a {expected_category} prompt, but got {normalized_prompt_id} ({actual_category or 'unknown'})"
            )

    def _is_system_prompt(self, prompt_id: str, prompt_data: dict | None = None) -> bool:
        if prompt_data and prompt_data.get("is_system"): return True
        return prompt_id in self._default_prompt_ids

    def _normalize_prompt_data(self, prompt_id: str, prompt_data: dict) -> dict:
        normalized = {
            "name": str((prompt_data or {}).get("name") or "").strip(),
            "description": str((prompt_data or {}).get("description") or "").strip(),
            "category": str((prompt_data or {}).get("category") or "task").strip() or "task",
            "attachment_kinds": list((prompt_data or {}).get("attachment_kinds") or []),
            "attachment_projection_overrides": dict((prompt_data or {}).get("attachment_projection_overrides") or {}),
            "system": str((prompt_data or {}).get("system") or ""),
            "user_template": str((prompt_data or {}).get("user_template") or ""),
        }
        normalized["is_system"] = self._is_system_prompt(prompt_id, normalized)
        if normalized["category"] not in self.prompt_categories:
            normalized["category"] = "task"
        normalized["attachment_kinds"] = self._normalize_attachment_kinds(normalized.get("attachment_kinds", []))
        normalized["attachment_projection_overrides"] = self._normalize_attachment_projection_overrides(
            normalized.get("attachment_projection_overrides", {}),
            normalized["attachment_kinds"],
        )
        return normalized

    def _slugify_prompt_name(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
        return slug or "custom_prompt"

    def _generate_custom_prompt_id(self, prompt_data: dict) -> str:
        category = str(prompt_data.get("category") or "task").strip() or "task"
        name_slug = self._slugify_prompt_name(prompt_data.get("name", ""))
        base_id = f"custom.{category}.{name_slug}"
        if base_id not in self.prompts and base_id not in self.custom_prompts: return base_id
        suffix = 2
        while True:
            candidate = f"{base_id}_{suffix}"
            if candidate not in self.prompts and candidate not in self.custom_prompts: return candidate
            suffix += 1

    def _normalize_prompt_map(self, prompt_map: dict) -> tuple[dict, bool]:
        normalized_prompts: dict = {}
        changed = False
        for prompt_id, prompt_data in (prompt_map or {}).items():
            if prompt_id in self._default_prompt_ids:
                changed = True
                logger.warning(f"AI 自定义提示词与系统模板冲突，已忽略: prompt_id={prompt_id}")
                continue
            if not isinstance(prompt_data, dict):
                changed = True
                continue
            try:
                normalized_prompt = self._normalize_prompt_data(prompt_id, prompt_data)
                self._validate_prompt_template(prompt_id, normalized_prompt)
                normalized_prompt["is_system"] = False
                normalized_prompts[prompt_id] = normalized_prompt
            except Exception as exc:
                changed = True
                logger.warning("跳过无效 AI 自定义提示词: prompt_id=%s 错误=%s", prompt_id, exc)
        return normalized_prompts, changed

    def _create_empty_definition_store(self) -> dict[str, Any]:
        return {
            "version": self.STORE_VERSION,
            "prompts": {},
            "assistants": {},
            "tasks": {},
        }

    def _build_definition_store_payload(self) -> dict[str, Any]:
        return {
            "version": self.STORE_VERSION,
            "prompts": deepcopy(self.custom_prompts),
            "assistants": deepcopy(self.assistant_overrides),
            "tasks": deepcopy(self.task_overrides),
        }

    def _extract_definition_sections(self, raw_store: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool]:
        if not isinstance(raw_store, dict):
            return {}, {}, {}, True

        prompts = raw_store.get("prompts", {})
        assistants = raw_store.get("assistants", {})
        tasks = raw_store.get("tasks", {})
        changed = (
            not isinstance(prompts, dict)
            or not isinstance(assistants, dict)
            or not isinstance(tasks, dict)
            or int(raw_store.get("version") or 0) != self.STORE_VERSION
        )
        return (
            prompts if isinstance(prompts, dict) else {},
            assistants if isinstance(assistants, dict) else {},
            tasks if isinstance(tasks, dict) else {},
            changed,
        )

    def ensure_default_files(self) -> None:
        """仅在首启时生成空定义仓库，避免覆盖已有用户编辑结果。"""
        if os.path.exists(self.definition_file):
            return

        logger.info("正在生成 AI 定义仓库文件。")
        self._save_json_to_disk(self.definition_file, self._create_empty_definition_store())

    def _save_json_to_disk(self, path: str, data: dict) -> None:
        tmp_path = f"{path}.tmp"
        try:
            with self._save_lock:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, path)
        except Exception as e:
            logger.error("保存 AI 定义配置文件失败: path=%s 错误=%s", path, e)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _persist_definition_store(self) -> None:
        self._save_json_to_disk(self.definition_file, self._build_definition_store_payload())

    def export_definition_store(self) -> dict[str, Any]:
        """导出当前内存态的标准化定义快照。"""
        return self._build_definition_store_payload()

    def reload(self) -> dict:
        """从磁盘重载并回写规范化后的 AI 定义。

        这里会顺手清洗旧版本字段、非法绑定和历史脏数据，因为定义文件是
        用户可编辑资产，长期运行后很容易出现结构漂移。
        """
        if not os.path.exists(self.definition_file):
            self.ensure_default_files()

        try:
            with open(self.definition_file, "r", encoding="utf-8") as f:
                raw_store = json.load(f)
        except Exception as e:
            logger.error("读取 AI 定义配置文件失败，将使用空定义继续: %s", e)
            raw_store = {}

        prompts_payload, assistants_payload, tasks_payload, store_changed = self._extract_definition_sections(raw_store)

        self.custom_prompts, custom_prompt_changed = self._normalize_prompt_map(prompts_payload)
        self.prompts = self._merge_runtime_prompts()
        self.assistant_overrides = self.normalize_assistant_overrides(assistants_payload or {})
        self.task_overrides = self.normalize_task_overrides(tasks_payload or {})
        self.assistants = self.get_runtime_assistants(self.assistant_overrides)
        self.tasks = self.get_runtime_tasks(self.task_overrides)

        normalized_store = self._build_definition_store_payload()
        if store_changed or custom_prompt_changed or normalized_store != raw_store:
            self._save_json_to_disk(self.definition_file, normalized_store)

        return {
            "prompts": self.prompts,
            "assistants": self.assistants,
            "tasks": self.tasks,
        }

    def save_prompt(self, prompt_id: str, prompt_data: dict) -> dict:
        """保存单个自定义 Prompt，并在持久化前完成校验与归一化。"""
        resolved_prompt_id = str(prompt_id or "").strip() or self._generate_custom_prompt_id(prompt_data)
        if resolved_prompt_id in self._default_prompt_ids:
            raise ValueError("系统模板只读，请勿直接修改内置模板")
        normalized_prompt = self._normalize_prompt_data(resolved_prompt_id, prompt_data)
        self._validate_prompt_template(resolved_prompt_id, normalized_prompt)
        normalized_prompt["is_system"] = False
        self.custom_prompts[resolved_prompt_id] = normalized_prompt
        self.prompts = self._merge_runtime_prompts()
        self._persist_definition_store()
        return {
            "prompt_id": resolved_prompt_id,
            "prompts": self.prompts,
        }

    def delete_prompt(self, prompt_id: str) -> dict:
        """删除单个自定义 Prompt。

        系统内置模板始终由代码维护，删除入口只允许作用于用户层覆写。
        """
        if prompt_id not in self.prompts:
            raise ValueError("Prompt ID 不存在")
        if self._is_system_prompt(prompt_id, self.prompts[prompt_id]):
            raise ValueError("无法删除系统内置模板")

        if prompt_id in self.custom_prompts:
            del self.custom_prompts[prompt_id]
        self.prompts = self._merge_runtime_prompts()
        self._persist_definition_store()
        return self.prompts

    def save_definition_store(self, definition_store: dict | None = None) -> dict:
        """批量保存 AI 定义集合。"""
        if not isinstance(definition_store, dict) or not all(
            key in definition_store for key in ("prompts", "assistants", "tasks")
        ):
            raise ValueError("AI 定义数据格式无效，必须包含 prompts、assistants、tasks 三个顶级字段")
        prompts_payload, assistants_payload, tasks_payload, _ = self._extract_definition_sections(definition_store or {})
        normalized_prompts, _ = self._normalize_prompt_map(prompts_payload)
        self.custom_prompts = normalized_prompts
        self.prompts = self._merge_runtime_prompts()
        self.assistant_overrides = self.normalize_assistant_overrides(assistants_payload)
        self.task_overrides = self.normalize_task_overrides(tasks_payload)
        self.assistants = self.get_runtime_assistants(self.assistant_overrides)
        self.tasks = self.get_runtime_tasks(self.task_overrides)
        self._persist_definition_store()
        return {
            "prompts": self.prompts,
            "assistants": self.assistants,
            "tasks": self.tasks,
        }

    def _normalize_assistant_override(self, assistant_id: str, override_data: dict | None = None) -> dict:
        default_data = dict(self.get_assistant_defaults().get(assistant_id) or {})
        if not default_data:
            raise ValueError(f"Unknown assistant definition: {assistant_id}")

        incoming_data = dict(override_data or {})
        prompt_id = str(incoming_data.get("prompt_id", default_data.get("prompt_id", "")) or "").strip()
        if not prompt_id:
            prompt_id = str(default_data.get("prompt_id") or "").strip()
        self._assert_prompt_binding(assistant_id, prompt_id, "assistant")

        normalized_assistant = AssistantDefinition.model_validate({
            **default_data,
            "id": assistant_id,
            "prompt_id": prompt_id,
            "tool_scope_selectable": incoming_data.get("tool_scope_selectable", default_data.get("tool_scope_selectable", [])),
        }).model_dump()

        return {
            "prompt_id": normalized_assistant["prompt_id"],
            "tool_scope_selectable": normalized_assistant["tool_scope_selectable"],
        }

    def _normalize_task_override(self, task_id: str, override_data: dict | None = None) -> dict:
        default_data = dict(self.get_task_defaults().get(task_id) or {})
        if not default_data:
            raise ValueError(f"Unknown task definition: {task_id}")

        incoming_data = dict(override_data or {})
        prompt_id = str(incoming_data.get("prompt_id", default_data.get("prompt_id", "")) or "").strip()
        if not prompt_id:
            prompt_id = str(default_data.get("prompt_id") or "").strip()
        self._assert_prompt_binding(task_id, prompt_id, "task")
        TaskDefinition.model_validate({
            **default_data,
            "id": task_id,
            "prompt_id": prompt_id,
        })
        return {"prompt_id": prompt_id}

    def get_runtime_assistants(self, assistant_overrides: dict | None = None) -> dict[str, dict]:
        """把系统默认助手与用户覆写合成为运行时快照。"""
        runtime = self.get_assistant_defaults()
        normalized_overrides = self.normalize_assistant_overrides(assistant_overrides or {})
        for assistant_id, override_data in normalized_overrides.items():
            base_data = dict(runtime.get(assistant_id) or {})
            base_data.update(override_data)
            base_data["is_system"] = True
            runtime[assistant_id] = AssistantDefinition.model_validate({
                "id": assistant_id,
                **base_data,
            }).model_dump()
        return runtime

    def get_runtime_tasks(self, task_overrides: dict | None = None) -> dict[str, dict]:
        """把系统默认任务与用户覆写合成为运行时快照。"""
        runtime = self.get_task_defaults()
        normalized_overrides = self.normalize_task_overrides(task_overrides or {})
        for task_id, override_data in normalized_overrides.items():
            base_data = dict(runtime.get(task_id) or {})
            base_data.update(override_data)
            base_data["is_system"] = True
            runtime[task_id] = TaskDefinition.model_validate({
                "id": task_id,
                **base_data,
            }).model_dump()
        return runtime

    def normalize_assistant_overrides(self, assistant_overrides: dict | None = None) -> dict[str, dict]:
        """过滤未知助手并把合法覆写规整成统一结构。"""
        normalized: dict[str, dict] = {}
        for assistant_id, override_data in (assistant_overrides or {}).items():
            if assistant_id not in self._default_assistant_ids or not isinstance(override_data, dict):
                continue
            normalized[assistant_id] = self._normalize_assistant_override(assistant_id, override_data)
        return normalized

    def normalize_task_overrides(self, task_overrides: dict | None = None) -> dict[str, dict]:
        """过滤未知任务并把合法覆写规整成统一结构。"""
        normalized: dict[str, dict] = {}
        for task_id, override_data in (task_overrides or {}).items():
            if task_id not in self._default_task_ids or not isinstance(override_data, dict):
                continue
            normalized[task_id] = self._normalize_task_override(task_id, override_data)
        return normalized

    def save_assistant_override(self, assistant_id: str, assistant_data: dict) -> tuple[dict, dict]:
        """保存单个助手覆写，并同步刷新运行时助手快照。"""
        normalized_overrides = self.normalize_assistant_overrides(self.assistant_overrides or {})
        normalized_overrides[assistant_id] = self._normalize_assistant_override(assistant_id, assistant_data)
        self.assistant_overrides = normalized_overrides
        self.assistants = self.get_runtime_assistants(normalized_overrides)
        self._persist_definition_store()
        return normalized_overrides, self.assistants

    def save_task_override(self, task_id: str, task_data: dict) -> tuple[dict, dict]:
        """保存单个任务覆写，并同步刷新运行时任务快照。"""
        normalized_overrides = self.normalize_task_overrides(self.task_overrides or {})
        normalized_overrides[task_id] = self._normalize_task_override(task_id, task_data)
        self.task_overrides = normalized_overrides
        self.tasks = self.get_runtime_tasks(normalized_overrides)
        self._persist_definition_store()
        return normalized_overrides, self.tasks

    def refresh_runtime_bindings(self) -> dict[str, Any]:
        """基于当前内存态覆写重新构建助手/任务运行时定义。"""
        self.assistants = self.get_runtime_assistants(self.assistant_overrides)
        self.tasks = self.get_runtime_tasks(self.task_overrides)
        return {
            "assistants": self.assistants,
            "tasks": self.tasks,
        }

    def get_definition_editor_meta(self) -> dict:
        """返回定义编辑器需要的静态元数据副本。

        这里统一返回深拷贝，避免前端调试或接口拼装时意外修改管理器内存态。
        """
        from backend.ai.ai_tools import get_tool_definitions

        return {
            "categories": deepcopy(self.prompt_categories),
            "attachments": deepcopy(self.attachment_definitions),
            "actions": deepcopy(self.action_definitions),
            "tools": deepcopy(get_tool_definitions()),
        }
