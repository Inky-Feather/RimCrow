"""
AI 管理器。

职责分层：
1. 委托 `AIDefinitionManager` 管理 AI 定义
2. 通用异步 AI 任务调用
3. 诊断型 Agent 流程（工具调用、流式输出、取消控制）
"""

import json
import asyncio
import re
import threading
import time
from typing import Any, Dict, List, Protocol, cast

from pydantic import TypeAdapter, ValidationError

from backend.ai.def_attachments import AttachmentResolver
from backend.ai.ai_contracts import (
    ModAliasGenerationItem,
    ResolvedContextAttachment,
    TaskDefinition,
)
from backend.ai.ai_definitions import AIDefinitionManager

from json_repair import repair_json

from backend.settings import DATA_DIR, AIConfig, settings
from backend.utils.logger import logger
from backend.utils.constants import get_lang_by_code
from backend.utils.event_bus import EventBus
from backend.ai.ai_gateway import LiteLLMGateway
from backend.ai.def_output_contracts import build_task_output_contract
from backend.ai.assistant_runtime import (
    AssistantRuntime,
    build_llm_kwargs,
    estimate_text_tokens,
    get_prompt_config,
    normalize_message_text,
    safe_format_template,
)


class _SupportsModelDump(Protocol):
    def model_dump(self) -> Any: ...

class AIManager:
    """全局单例 AI 管理器。"""

    _instance = None
    
    def __new__(cls):
        """实现单例模式，确保全局只保留一个 AI 管理器实例。"""
        if cls._instance is None:
            cls._instance = super(AIManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化运行期状态、LLM 网关和本地 Prompt 仓库。"""
        if self._initialized: return
        self._initialized = True
        self.llm = LiteLLMGateway()
        self._cancel_lock = threading.Lock()
        # AI 异步任务与诊断任务共享同一套“取消令牌”模型，保证前端全局任务栏可以统一打断。
        self._cancelled_task_ids: set[str] = set()
        
        # Prompt / Assistant / Task 的用户定义统一保存在独立 AI 定义文件中；
        # 全局 settings.ai 只保留连接与运行参数，不再保存这些静态定义覆写。
        self.definition_manager = AIDefinitionManager(str(DATA_DIR / "ai_definitions.json"))
        self.attachment_resolver = AttachmentResolver(self.definition_manager, self.llm)
        self._reload_runtime_bindings()
        self.assistant_runtime = AssistantRuntime(self.definition_manager, self.llm)
        self._structured_output_adapters = {
            "task.mod_alias_generation": TypeAdapter(list[ModAliasGenerationItem]),
        }
        
        logger.info("AI 管理器初始化完成。")

    def _coerce_int(self, value: Any, default: int) -> int:
        """把动态来源的数值安全收口为 int，避免静态类型和运行时都不稳定。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _dump_model_like(self, value: Any) -> Any:
        """把 pydantic 风格对象收口成原生可序列化结构。"""
        if value is None:
            return None
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return cast("_SupportsModelDump", value).model_dump()
        if isinstance(value, list):
            return [self._dump_model_like(item) for item in value]
        return value

    def _get_ai_config(self) -> AIConfig:
        raw_cfg = settings.config.ai
        return AIConfig(**raw_cfg) if isinstance(raw_cfg, dict) else raw_cfg

    def _reload_runtime_bindings(self) -> dict[str, Any]:
        return self.definition_manager.reload()

    # =========================================================================
    # 公开能力：厂商 / 模型探测
    # =========================================================================
    def get_providers(self) -> List[Dict[str, str]]:
        """返回前端 AI 设置页所需的协议列表。"""
        return self.llm.get_providers()

    def get_models(self, config_dict: dict) -> List[str]:
        """根据临时配置探测模型列表。"""
        return self.llm.get_models(config_dict)

    def get_model_capabilities(self, config_dict: dict) -> dict[str, Any]:
        """返回当前临时配置对应的模型能力摘要。"""
        return self.llm.get_model_capabilities(config_dict)

    def get_model_capability_meta(self) -> dict[str, Any]:
        """返回前端本地模型能力判断所需的静态元数据。"""
        return self.llm.get_model_capability_meta()

    # =========================================================================
    # 通用基础工具
    # =========================================================================
    def _get_llm_kwargs(self, override_config: dict | None = None) -> dict:
        """委托网关统一组装 LLM 调用参数。"""
        return build_llm_kwargs(self.llm, override_config)

    def _extract_json_from_text(self, text: str, is_batch: bool = False):
        """
        利用 json_repair 库进行究极容错解析
        """
        try:
            # repair_json 能自动处理 Markdown 代码块、未转义引号、缺少闭合括号等问题
            # return_objects=True 直接返回 Python 对象
            parsed = repair_json(text, return_objects=True)
            
            # 兼容性处理：有时候 AI 会自作聪明只返回对象没返回数组
            if isinstance(parsed, dict): return [parsed] if is_batch else parsed
            if isinstance(parsed, list): return parsed
                
            # 如果解析出来既不是 list 也不是 dict (比如解析成了空字符串)
            return None
        except Exception as e:
            logger.error(
                "AI 结构化输出解析失败，已放弃 JSON 修复。",
                extra={"error_code": "AI.STRUCTURED.JSON_REPAIR_FAILED", "extra_context": {"original_error": str(e), "raw_preview": text[:200]}},
            )
            return None

    def _parse_structured_output(self, task_key: str, text: str) -> Any:
        """按任务类型做结构化输出校验；失败时退回宽松解析。"""
        adapter = self._structured_output_adapters.get(task_key)
        if not adapter: return self._extract_json_from_text(text, is_batch=(task_key == "task.mod_alias_generation"))

        try:
            parsed = adapter.validate_json(text)
            # 对外仍返回原生 dict/list，避免调用方被迫感知 pydantic 模型。
            return self._dump_model_like(parsed)
        except ValidationError as e:
            logger.warning(
                "[AI结构化输出] 校验失败，准备退回宽松解析。task=%s",
                task_key,
                extra={"error_code": "AI.STRUCTURED.VALIDATION_FAILED", "extra_context": {"task_key": task_key, "original_error": str(e)}},
            )
            return self._extract_json_from_text(text, is_batch=(task_key == "task.mod_alias_generation"))

    def _normalize_mod_alias_generation_output(
        self,
        parsed: Any,
        expected_ids: set[str] | None = None,
    ) -> list[dict[str, str]]:
        """归一化模组别名生成结果。

        目标是把“部分可用”的模型输出收口成稳定结构：
        - 只接受对象列表
        - `package_id` 必须存在
        - `alias_name` / `notes` 缺失时补空串，而不是整条判失败
        - 如给定 `expected_ids`，则顺手过滤越界结果
        """
        if not isinstance(parsed, list): return []

        normalized_items: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            package_id = str(item.get("package_id") or "").strip().lower()
            if not package_id:
                continue
            if expected_ids is not None and package_id not in expected_ids:
                continue
            alias_name = str(item.get("alias_name") or "").strip()
            notes = str(item.get("notes") or "").strip()
            if not alias_name and not notes:
                continue
            if package_id in seen_ids:
                continue
            seen_ids.add(package_id)
            normalized_items.append(
                {
                    "package_id": package_id,
                    "alias_name": alias_name,
                    "notes": notes,
                }
            )
        return normalized_items

    def _normalize_mod_alias_generation_input_payload(self, parsed: Any) -> list[dict[str, str]]:
        """归一化模组别名任务输入负载。"""
        if not isinstance(parsed, list): return []

        normalized_items: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            package_id = str(item.get("package_id") or "").strip().lower()
            if not package_id or package_id in seen_ids:
                continue
            seen_ids.add(package_id)
            normalized_items.append(
                {
                    "package_id": package_id,
                    "name": str(item.get("name") or "").strip(),
                    "description": str(item.get("description") or "").strip(),
                }
            )
        return normalized_items

    def _estimate_text_tokens(self, text: str, model_name: str) -> int:
        """
        使用后端统一的 tokenizer 估算文本 Token。
        这里的结果用于诊断链路的全局 Token 统计，比前端按字符粗算更稳定。
        """
        return estimate_text_tokens(self.llm, text, model_name)

    def _message_text(self, content: Any) -> str:
        """把运行期消息内容统一规整成纯文本。"""
        return normalize_message_text(self.llm, content)

    def _normalize_reasoning_content(self, reasoning_content: Any) -> str:
        """将历史里的 reasoning_content 规整为可回灌的纯文本。

        部分推理模型在 thinking / reasoning 模式下要求：
        - 如果上一轮 assistant 暴露了 reasoning_content
        - 后续继续调用工具或继续追问时，必须把这段内容原样回传

        因此这里单独保留一份规整逻辑，避免它在历史消息构建阶段被悄悄丢掉。
        """
        return self._message_text(reasoning_content)

    def _extract_reasoning_content(self, obj: Any) -> str:
        """兼容 reasoning_content 与部分本地兼容层的 reasoning 字段。"""
        reasoning_content = getattr(obj, "reasoning_content", None)
        if reasoning_content is None or reasoning_content == "":
            reasoning_content = getattr(obj, "reasoning", "")
        return self._normalize_reasoning_content(reasoning_content)

    def _split_inline_reasoning_from_content(self, content: str, existing_reasoning: str = "") -> tuple[str, str]:
        """兼容本地模型把 <think>...</think> 混在正文开头返回。"""
        normalized_content = str(content or "")
        match = re.match(r"^\s*<think>\s*([\s\S]*?)\s*</think>\s*", normalized_content, flags=re.IGNORECASE)
        if not match:
            return normalized_content, str(existing_reasoning or "")

        inline_reasoning = match.group(1).strip()
        remaining_content = normalized_content[match.end():]
        reasoning_parts = [part for part in (str(existing_reasoning or "").strip(), inline_reasoning) if part]
        return remaining_content, "\n".join(reasoning_parts)

    def _build_prompt_messages(
        self,
        prompt_config: dict,
        variables: dict,
        history: list[dict] | None = None,
    ) -> list[dict]:
        """根据 prompt 配置、变量和历史消息生成最终 messages。"""
        system_prompt = self._safe_format(prompt_config.get("system", ""), variables)
        user_prompt = self._safe_format(prompt_config.get("user_template", ""), variables)

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history or []:
            if msg.get("role") in ("user", "assistant"):
                normalized_msg = {
                    "role": msg["role"],
                    "content": self._message_text(msg.get("content", "")),
                }
                messages.append(normalized_msg)
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _build_task_output_contract(self, task_key: str) -> str:
        """按任务定义返回统一输出协议，避免把结构约束散落到具体提示词。"""
        return build_task_output_contract(task_key)

    def _build_task_prompt_config(self, base_prompt_config: dict, task_key: str) -> dict:
        """为单次任务统一追加运行时协议约束。"""
        prompt_config = dict(base_prompt_config or {})
        system_text = str(prompt_config.get("system") or "")
        output_contract = self._build_task_output_contract(task_key)
        prompt_config["system"] = f"{system_text}\n\n{output_contract}".strip() if output_contract else system_text
        return prompt_config

    def _safe_format(self, template: str, variables: dict) -> str:
        """
        安全格式化工具：只替换模板中存在的变量，忽略其他大括号。
        解决 JSON 示例与 Python .format() 的冲突。
        """
        return safe_format_template(template, variables)

    def _build_task_runtime_variables(self, variables: Dict[str, Any] | None = None) -> dict[str, Any]:
        """统一补齐单次任务运行期变量。

        当前统一收口两类常用上下文：
        1. 基础语言变量
        2. 可选的附件/附加块占位符，便于单次任务也复用统一模板机制
        """
        runtime_variables = dict(variables or {})
        runtime_variables.setdefault("target_lang", get_lang_by_code(settings.config.language))
        runtime_variables.setdefault("current_time", time.strftime("%Y-%m-%d %H:%M:%S"))
        runtime_variables.setdefault("attachments_block", "")
        return runtime_variables

    def get_trace_records(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """返回 assistant 会话级链路视图。"""
        return self.assistant_runtime.get_trace_records(session_id)

    # =========================================================================
    #  核心：单次同步执行 (供简单的闲聊或单次测试使用)
    # =========================================================================
    def _get_task_definition(self, task_id: str) -> TaskDefinition:
        """读取并校验单个任务定义。"""
        task_data = self.definition_manager.tasks.get(task_id)
        if not task_data:
            raise ValueError(f"Task definition '{task_id}' not found.")
        task = TaskDefinition.model_validate(task_data)
        prompt_data = self._get_prompt_config(task.prompt_id)
        if prompt_data.get("category") != "task":
            raise ValueError(f"Task definition '{task_id}' must bind a task prompt, got '{task.prompt_id}'.")
        return task

    def _build_task_execution_context(
        self,
        task_key: str,
        payload: Dict[str, Any] | None = None,
        override_config: dict | None = None,
    ) -> dict[str, Any]:
        """统一构建异步任务运行上下文。"""
        task_definition = self._get_task_definition(task_key)
        prompt_id = task_definition.prompt_id
        if prompt_id not in self.prompts:
            raise ValueError(f"Prompt template '{prompt_id}' not found.")

        payload = dict(payload or {})
        runtime_variables = self._build_task_runtime_variables(payload.get("variables"))
        resolved_attachments = self.attachment_resolver.resolve_many(
            {"attachments": list(payload.get("attachments", []) or [])},
            prompt_id=prompt_id,
        )
        runtime_variables["attachments_block"] = self.attachment_resolver.build_prompt_block(resolved_attachments)
        runtime_variables.update(self.attachment_resolver.extract_prompt_variables(resolved_attachments))
        prompt_config = self._build_task_prompt_config(self.prompts[prompt_id], task_key)
        if prompt_config.get("category") != "task":
            raise ValueError(f"Task '{task_key}' must bind a task prompt, got '{prompt_id}'.")
        effective_override = {"enable_reasoning": False}
        if override_config:
            effective_override.update(override_config)
        llm_kwargs = self._get_llm_kwargs(effective_override)

        return {
            "task_definition": task_definition,
            "prompt_id": prompt_id,
            "prompt_config": prompt_config,
            "runtime_variables": runtime_variables,
            "resolved_attachments": resolved_attachments,
            "llm_kwargs": llm_kwargs,
        }

    def _resolve_mod_alias_generation_input_items(
        self,
        resolved_attachments: list[ResolvedContextAttachment],
        runtime_variables: dict[str, Any],
    ) -> list[dict[str, str]]:
        """把模组别名任务输入统一规整成稳定的模组列表。"""
        existing_input_json = str(runtime_variables.get("mod_alias_input_json") or "").strip()
        if existing_input_json:
            parsed_existing = self._extract_json_from_text(existing_input_json, is_batch=True)
            return self._normalize_mod_alias_generation_input_payload(parsed_existing)

        normalized_items: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for attachment in resolved_attachments or []:
            if attachment.type != "mod_selection":
                continue
            facts = dict(attachment.facts or {}) if isinstance(attachment.facts, dict) else {}
            mods = facts.get("mods", [])
            if not isinstance(mods, list):
                mods = []
            for mod in mods:
                if not isinstance(mod, dict):
                    continue
                package_id = str(mod.get("package_id") or "").strip().lower()
                if not package_id or package_id in seen_ids:
                    continue
                seen_ids.add(package_id)
                normalized_items.append({
                    "package_id": package_id,
                    "name": str(mod.get("name") or runtime_variables.get("name") or "").strip(),
                    "description": str(mod.get("description") or runtime_variables.get("description") or "").strip(),
                })
        return normalized_items

    def _resolve_mod_alias_chunk_token_budget(
        self,
        *,
        cfg: AIConfig,
        model_name: str,
        prompt_config: dict,
        runtime_variables: dict[str, Any],
    ) -> tuple[int, int]:
        """估算模组别名批处理的输入分块预算。

        `max_output_tokens` 是输出上限，不等于模型上下文窗口。若配置里提供
        `max_input_tokens` 或 `context_window_tokens`，优先使用更明确的输入预算。
        """
        resolve_output_tokens = getattr(cfg, "resolved_max_output_tokens", None)
        resolved_output_value = (
            resolve_output_tokens()
            if callable(resolve_output_tokens)
            else getattr(cfg, "max_output_tokens", 0)
        )
        output_token_budget = max(
            256,
            self._coerce_int(resolved_output_value or 4096, 4096),
        )
        resolve_input_tokens = getattr(cfg, "resolved_max_input_tokens", None)
        if callable(resolve_input_tokens):
            request_input_budget = self._coerce_int(resolve_input_tokens(), 0)
        else:
            explicit_input_budget = self._coerce_int(getattr(cfg, "max_input_tokens", 0) or 0, 0)
            context_window_tokens = self._coerce_int(getattr(cfg, "context_window_tokens", 0) or 0, 0)
            if explicit_input_budget > 0:
                request_input_budget = explicit_input_budget
            elif context_window_tokens > 0:
                request_input_budget = max(1000, context_window_tokens - output_token_budget - 512)
            else:
                request_input_budget = max(2000, min(12000, output_token_budget * 2))

        try:
            probe_variables = dict(runtime_variables or {})
            probe_variables["mod_alias_input_json"] = "[]"
            base_messages = self._build_prompt_messages(prompt_config, probe_variables)
            base_prompt_tokens = self.llm.estimate_messages_tokens(base_messages, model_name)
        except Exception as exc:
            logger.debug(f"[AI任务] 分块基础 Prompt Token 估算失败，使用保守预算: {exc}")
            base_prompt_tokens = 0

        chunk_item_budget = max(500, int(request_input_budget) - int(base_prompt_tokens or 0) - 256)
        max_item_tokens = max(300, chunk_item_budget - 200)
        return chunk_item_budget, max_item_tokens

    def execute_structured_task(
        self,
        task_key: str,
        payload: Dict[str, Any] | None = None,
        override_config: dict | None = None,
    ) -> Any:
        """同步执行单次结构化任务。

        用于翻译这类即时请求：复用 AI Task / Prompt / 输出契约，
        但不进入异步任务栏、分块重试或附件专用流程。
        """
        context = self._build_task_execution_context(task_key, payload, override_config)
        prompt_config = dict(context["prompt_config"] or {})
        runtime_variables = dict(context["runtime_variables"] or {})
        llm_kwargs = dict(context["llm_kwargs"] or {})

        messages = self._build_prompt_messages(prompt_config, runtime_variables)
        response = self.llm.completion(messages=messages, llm_kwargs=llm_kwargs)
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ValueError("AI 任务没有返回有效内容")
        message_obj = choices[0].message  # type: ignore
        result_text = self._message_text(getattr(message_obj, "content", ""))
        parsed_json = self._parse_structured_output(task_key, result_text)
        if parsed_json is None:
            raise ValueError("AI 任务返回格式无效")
        return parsed_json

    # =========================================================================
    #  核心：异步任务执行引擎
    # =========================================================================
    async def _process_mod_alias_generation_chunk(
        self,
        *,
        chunk_id: str,
        task_key: str,
        chunk_data: List[Dict[str, Any]],
        prompt_config: dict,
        runtime_variables: dict[str, Any],
        llm_kwargs: dict,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        """处理单个模组别名生成分块，负责并发限流、请求重试和结果解析。"""
        async with semaphore:
            try:
                chunk_variables = dict(runtime_variables or {})
                chunk_variables["mod_alias_input_json"] = json.dumps(chunk_data, ensure_ascii=False)
                messages = self._build_prompt_messages(prompt_config, chunk_variables)
                response = await self.llm.acompletion(
                    messages=messages,
                    llm_kwargs=llm_kwargs,
                    num_retries=3,
                )
                result_text = self._message_text(response.choices[0].message.content)  # type: ignore
                parsed_json = self._parse_structured_output(task_key, result_text)  # type: ignore[arg-type]
                expected_ids = {
                    str(item.get("package_id") or "").strip().lower()
                    for item in chunk_data
                    if item.get("package_id")
                }
                normalized_data = self._normalize_mod_alias_generation_output(
                    parsed_json,
                    expected_ids=expected_ids,
                )
                return {"chunk_id": chunk_id, "status": "success", "data": normalized_data, "raw": result_text}
            except Exception as exc:
                logger.error(
                    "AI 分块请求多次重试后仍失败。chunk_id=%s task=%s item_count=%s",
                    chunk_id,
                    task_key,
                    len(chunk_data),
                    extra={
                        "error_code": "AI.TASK.CHUNK_FAILED",
                        "extra_context": {
                            "chunk_id": chunk_id,
                            "task_key": task_key,
                            "item_count": len(chunk_data),
                            "original_error": str(exc),
                        },
                    },
                )
                return {"chunk_id": chunk_id, "status": "error", "error": str(exc), "data": None}

    async def execute_task_async(self, task_key: str, payload: Dict[str, Any], task_id: str) -> dict[str, Any]:
        """统一异步任务调度中心。"""
        context = self._build_task_execution_context(task_key, payload)
        task_definition: TaskDefinition = context["task_definition"]
        prompt_config = dict(context["prompt_config"] or {})
        runtime_variables = dict(context["runtime_variables"] or {})
        llm_kwargs = dict(context["llm_kwargs"] or {})

        if task_key != "task.mod_alias_generation":
            raise ValueError(f"Unsupported async task: {task_key}")

        items = self._resolve_mod_alias_generation_input_items(
            context["resolved_attachments"],
            runtime_variables,
        )
        if not items:
            raise ValueError("模组别名任务缺少有效的模组输入")

        raw_cfg = settings.config.ai
        cfg = AIConfig(**raw_cfg) if isinstance(raw_cfg, dict) else raw_cfg
        model_name = str(llm_kwargs.get("model", settings.config.ai.model) or settings.config.ai.model)
        max_concurrency = getattr(cfg, "max_concurrency", 3)
        max_attempts = 3
        runtime_variables["mod_alias_input_json"] = json.dumps(items, ensure_ascii=False)

        task_meta = {
            "task_id": str(task_id or "").strip(),
            "task_key": task_key,
            "title": str(task_definition.name or "AI 任务").strip() or "AI 任务",
            "created_at": int(time.time() * 1000),
            "input_total": len(items),
            "max_attempts": max_attempts,
        }

        safe_input_tokens, max_item_tokens = self._resolve_mod_alias_chunk_token_budget(
            cfg=cfg,
            model_name=model_name,
            prompt_config=prompt_config,
            runtime_variables=runtime_variables,
        )

        def estimate_item_tokens(item: Dict[str, Any]) -> int:
            """按当前模型口径估算单条输入会占用多少 token。"""
            return self._estimate_text_tokens(json.dumps(item, ensure_ascii=False), model_name)

        def fit_item_to_budget(raw_item: Dict[str, Any]) -> Dict[str, Any]:
            """尽量保留关键信息地把单条输入裁进 token 预算。

            当前只裁剪 description，因为 package_id/name 是结果对齐和可读性
            的核心锚点，不能为了省 token 把它们也丢掉。
            """
            item = dict(raw_item or {})
            if estimate_item_tokens(item) <= max_item_tokens: return item

            description = str(item.get("description") or "").strip()
            if not description: return item

            suffix = "...(截断)"
            low, high = 0, len(description)
            best_description = ""
            while low <= high:
                mid = (low + high) // 2
                candidate = dict(item)
                candidate["description"] = f"{description[:mid].rstrip()}{suffix}" if mid < len(description) else description
                if estimate_item_tokens(candidate) <= max_item_tokens:
                    best_description = candidate["description"]
                    low = mid + 1
                else:
                    high = mid - 1

            item["description"] = best_description
            if estimate_item_tokens(item) <= max_item_tokens: return item
            item.pop("description", None)
            return item

        def build_smart_chunks(items_to_chunk: List[Dict[str, Any]]) -> list[list[dict[str, Any]]]:
            """按估算 token 动态分块，避免固定条数导致大批次溢出。"""
            chunks_list: list[list[dict[str, Any]]] = []
            current_chunk: list[dict[str, Any]] = []
            current_chunk_tokens = 0
            for raw_item in items_to_chunk:
                item = fit_item_to_budget(dict(raw_item or {}))
                item_tokens = estimate_item_tokens(item)
                if current_chunk_tokens + item_tokens > safe_input_tokens and current_chunk:
                    chunks_list.append(current_chunk)
                    current_chunk = [item]
                    current_chunk_tokens = item_tokens
                else:
                    current_chunk.append(item)
                    current_chunk_tokens += item_tokens
            if current_chunk:
                chunks_list.append(current_chunk)
            return chunks_list

        all_results_by_id: dict[str, dict[str, Any]] = {}
        successful_ids: set[str] = set()
        attempt_counts_by_id = {
            str(item.get("package_id") or "").strip().lower(): 0
            for item in items
            if item.get("package_id")
        }
        pending_items = [dict(item) for item in items if item.get("package_id")]
        attempt_count = 0

        logger.info("AI 任务开始。task_id=%s task=%s total=%s", task_id, task_key, len(pending_items))

        try:
            while pending_items:
                self._raise_if_task_cancelled(task_id)
                attempt_count += 1
                chunks = build_smart_chunks(pending_items)
                semaphore = asyncio.Semaphore(max_concurrency)
                logger.info(
                    "AI 任务进入新一轮请求。task_id=%s attempt=%s pending=%s chunks=%s",
                    task_id,
                    attempt_count,
                    len(pending_items),
                    len(chunks),
                )
                chunk_tasks: list[tuple[asyncio.Task, list[dict[str, Any]]]] = []
                for index, chunk in enumerate(chunks):
                    self._raise_if_task_cancelled(task_id)
                    coroutine = self._process_mod_alias_generation_chunk(
                        chunk_id=f"a{attempt_count}_c{index}",
                        task_key=task_key,
                        chunk_data=chunk,
                        prompt_config=prompt_config,
                        runtime_variables=runtime_variables,
                        llm_kwargs=llm_kwargs,
                        semaphore=semaphore,
                    )
                    chunk_tasks.append((asyncio.create_task(coroutine), chunk))

                for future, original_chunk in chunk_tasks:
                    try:
                        result = await future
                    except asyncio.CancelledError as exc:
                        raise AITaskRequestCancelled(f"AI task cancelled: {task_id}") from exc
                    self._raise_if_task_cancelled(task_id)

                    expected_ids = {
                        str(item.get("package_id") or "").strip().lower()
                        for item in original_chunk
                        if item.get("package_id")
                    }
                    if result["status"] == "success" and isinstance(result.get("data"), list):
                        valid_data: list[dict[str, Any]] = []
                        for normalized_item in result["data"]:
                            if not isinstance(normalized_item, dict):
                                continue
                            package_id = str(normalized_item.get("package_id") or "").strip().lower()
                            if package_id not in expected_ids:
                                continue
                            valid_data.append(normalized_item)
                            successful_ids.add(package_id)
                            all_results_by_id[package_id] = normalized_item
                        if valid_data:
                            EventBus.emit("ai-task-result-chunk", {
                                "task_id": task_id,
                                "items": valid_data,
                                "meta": {
                                    **task_meta,
                                    "attempt_count": attempt_count,
                                },
                            })

                    progress = min(95, int((len(successful_ids) / max(1, len(items))) * 100))
                    EventBus.emit_progress(
                        task_id,
                        "ai-task",
                        status="running",
                        progress=progress,
                        message=f"正在推理... [第{attempt_count}轮] 成功: {len(successful_ids)}/{len(items)}",
                        metrics={
                            **task_meta,
                            "attempt_count": attempt_count,
                            "current": len(successful_ids),
                            "resolved_count": len(successful_ids),
                            "failed_count": max(0, len(items) - len(successful_ids)),
                        },
                    )

                unresolved_ids = {
                    str(item.get("package_id") or "").strip().lower()
                    for item in pending_items
                    if str(item.get("package_id") or "").strip().lower() not in successful_ids
                }
                for package_id in unresolved_ids:
                    attempt_counts_by_id[package_id] = int(attempt_counts_by_id.get(package_id, 0) or 0) + 1

                pending_items = [
                    dict(item)
                    for item in items
                    if (package_id := str(item.get("package_id") or "").strip().lower())
                    and package_id not in successful_ids
                    and int(attempt_counts_by_id.get(package_id, 0) or 0) < max_attempts
                ]
                if pending_items:
                    self._raise_if_task_cancelled(task_id)
                    await asyncio.sleep(1)
        except AITaskRequestCancelled:
            EventBus.emit_progress(
                task_id,
                "ai-task",
                status="cancelled",
                progress=0,
                message="AI 任务已取消",
                metrics={
                    **task_meta,
                    "attempt_count": attempt_count,
                    "resolved_count": len(successful_ids),
                    "failed_count": max(0, len(items) - len(successful_ids)),
                },
            )
            return {
                "cancelled": True,
                "meta": {
                    **task_meta,
                    "attempt_count": attempt_count,
                    "resolved_count": len(successful_ids),
                    "failed_count": max(0, len(items) - len(successful_ids)),
                },
                "results": list(all_results_by_id.values()),
            }
        finally:
            self._clear_cancelled_task(task_id)

        failed_results: list[dict[str, Any]] = []
        for item in items:
            package_id = str(item.get("package_id") or "").strip().lower()
            if not package_id or package_id in successful_ids:
                continue
            failed_results.append({
                "package_id": package_id,
                "alias_name": "",
                "notes": "",
                "_failed": True,
                "_attempt_count": int(attempt_counts_by_id.get(package_id, 0) or 0),
            })
        if failed_results:
            EventBus.emit("ai-task-result-chunk", {
                "task_id": task_id,
                "items": failed_results,
                "meta": {
                    **task_meta,
                    "attempt_count": attempt_count,
                },
            })

        final_results = [*list(all_results_by_id.values()), *failed_results]
        failed_count = len(failed_results)
        EventBus.emit_progress(
            task_id,
            "ai-task",
            status="success",
            progress=100,
            message=f"推理结束！成功: {len(successful_ids)}, 失败: {failed_count}",
            metrics={
                **task_meta,
                "attempt_count": attempt_count,
                "resolved_count": len(successful_ids),
                "failed_count": failed_count,
                "current": len(successful_ids),
            },
        )
        return {
            "meta": {
                **task_meta,
                "attempt_count": attempt_count,
                "resolved_count": len(successful_ids),
                "failed_count": failed_count,
            },
            "results": final_results,
            "success_count": len(successful_ids),
            "failed_count": failed_count,
        }

    def cancel_task(self, task_id: str) -> bool:
        """标记某个 AI 异步任务为已取消，等待异步循环在安全点退出。"""
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id: return False
        with self._cancel_lock:
            self._cancelled_task_ids.add(normalized_task_id)
        logger.info(f"[AI任务] 收到取消请求 task_id={normalized_task_id}")
        return True

    def _clear_cancelled_task(self, task_id: str) -> None:
        if not task_id: return
        with self._cancel_lock:
            self._cancelled_task_ids.discard(task_id)

    def _is_task_cancelled(self, task_id: str) -> bool:
        if not task_id: return False
        with self._cancel_lock: return task_id in self._cancelled_task_ids

    def _raise_if_task_cancelled(self, task_id: str) -> None:
        if self._is_task_cancelled(task_id):
            raise AITaskRequestCancelled(f"AI task cancelled: {task_id}")

    # =========================================================================
    # 通用测试入口
    # =========================================================================
    def test_chat(self, message: str, override_config: dict) -> dict[str, Any]:
        """
        用于前端“测试模型”按钮的方法。

        这里会主动把 temperature 留空、输出上限压到很小，
        目的是尽量用最低成本验证“能否通”和“接口是否兼容”。
        """
        safe_override = dict(override_config or {})
        # 测试按钮默认关闭深度思考，也不强传 temperature。
        safe_override["enable_reasoning"] = bool(safe_override.get("enable_reasoning", False))
        # 测试按钮默认不强传 temperature
        safe_override["temperature"] = None
        # 测试只要极小输出即可。
        test_output_tokens = min(
            int(safe_override.get("max_output_tokens") or 64),
            64,
        )
        safe_override["max_output_tokens"] = test_output_tokens
        # 默认自动 endpoint 选择
        safe_override["endpoint_mode"] = safe_override.get("endpoint_mode") or "auto"
        llm_kwargs = self._get_llm_kwargs(safe_override)
        messages = [{"role": "user", "content": message}]
        try:
            response = self.llm.completion(messages=messages, llm_kwargs=llm_kwargs)
            choices = getattr(response, "choices", None) or []
            if not choices:
                response_summary = ""
                try:
                    response_summary = json.dumps(
                        self._dump_model_like(response) or getattr(response, "__dict__", {}),
                        ensure_ascii=False,
                        default=str,
                    )[:800]
                except Exception:
                    response_summary = str(response)[:800]
                raise ValueError(
                    "模型接口返回了非 OpenAI Chat Completions 兼容格式或空 choices。"
                    "请确认当前 Base URL 指向 /v1 兼容接口，并检查模型名/协议是否匹配。"
                    f"响应摘要: {response_summary}"
                )
            message_obj = choices[0].message  # type: ignore
            content_text, reasoning_text = self._split_inline_reasoning_from_content(
                self._message_text(getattr(message_obj, "content", "")),
                self._extract_reasoning_content(message_obj),
            )

            raw_message = {
                "content": getattr(message_obj, "content", ""),
                "reasoning_content": getattr(message_obj, "reasoning_content", ""),
                "reasoning": getattr(message_obj, "reasoning", ""),
                "tool_calls": getattr(message_obj, "tool_calls", None),
            }
            result = {
                "text": content_text,
                "reasoning_content": reasoning_text,
                "is_reasoning_only": False,
                "raw_message": raw_message,
                "request_meta": {
                    "model": llm_kwargs.get("model", ""),
                    "provider": llm_kwargs.get("_rmm_provider", ""),
                    "base_url": llm_kwargs.get("_rmm_base_url", ""),
                    "endpoint_mode": llm_kwargs.get("_rmm_endpoint_mode", ""),
                    "enable_reasoning": bool(llm_kwargs.get("_rmm_enable_reasoning", False)),
                    "reasoning_effort": llm_kwargs.get("_rmm_reasoning_effort", "medium"),
                },
            }
            if content_text.strip(): return result

            # 一些推理模型或兼容层在测试请求里可能只返回 reasoning_content，
            # 如果直接把它当空串返回，前端只会看到“成功但没有任何内容”，难以排障。
            if reasoning_text.strip():
                result["is_reasoning_only"] = True
                result["text"] = (
                    "模型已成功返回推理内容，但没有产出最终正文。\n\n"
                    "这通常说明当前模型/网关的测试请求格式与正式对话格式并不完全一致，"
                    "或该模型更适合在助手会话中使用。\n\n"
                    f"reasoning_content:\n{reasoning_text}"
                )
                return result
            return result
        except Exception as e:
            logger.error(
                "AI 测试对话失败：%s",
                e,
                exc_info=True,
                extra={"error_code": "AI.TEST_CHAT.FAILED", "extra_context": {"original_error": str(e)}},
            )
            err_text = str(e)
            err_lower = err_text.lower()
            if "unknown provider for model" in err_lower:
                raise Exception(
                    "请求失败：当前代理接口无法正确路由这个模型。"
                    "很可能该模型需要走 /v1/responses，或者该中转尚未为此模型配置 provider 映射。"
                ) from e
            if "temperature" in err_lower and "unsupported" in err_lower:
                raise Exception(
                    "请求失败：当前模型不接受你传入的 temperature。"
                    "建议将 temperature 留空，或使用自动兼容模式。"
                ) from e
            raise Exception("请求失败：AI 服务没有返回可用结果。请检查模型名称、Base URL、API Key、代理设置和服务状态。") from e
        


    # =========================================================================
    # Prompt 管理委托层
    # =========================================================================

    def save_prompt(self, prompt_id: str, prompt_data: dict):
        """新增或更新单个 Prompt。"""
        prompts = self.definition_manager.save_prompt(prompt_id, prompt_data)
        self._reload_runtime_bindings()
        return prompts

    def delete_prompt(self, prompt_id: str):
        """删除单个 Prompt。"""
        prompts = self.definition_manager.delete_prompt(prompt_id)
        self._reload_runtime_bindings()
        return prompts

    def save_assistant(self, assistant_id: str, assistant_data: dict):
        """保存系统助手的用户可配置覆写。"""
        _, runtime_assistants = self.definition_manager.save_assistant_override(
            assistant_id,
            assistant_data,
        )
        return runtime_assistants

    def save_task(self, task_id: str, task_data: dict):
        """保存系统任务的用户可配置覆写。"""
        _, runtime_tasks = self.definition_manager.save_task_override(
            task_id,
            task_data,
        )
        return runtime_tasks

    @property
    def prompts(self) -> dict:
        """对外暴露当前 Prompt 字典。"""
        return self.definition_manager.prompts

    @property
    def assistants(self) -> dict:
        """对外暴露当前助手定义字典。"""
        return self.definition_manager.assistants

    @property
    def tasks(self) -> dict:
        """对外暴露当前任务定义字典。"""
        return self.definition_manager.tasks

    @property
    def definition_editor_meta(self) -> dict:
        """对外暴露 AI 定义编辑器所需的系统元数据。"""
        return self.definition_manager.get_definition_editor_meta()

    def _get_prompt_config(self, prompt_id: str) -> dict:
        """读取指定 prompt 配置。"""
        return get_prompt_config(self.prompts, prompt_id)

    # =========================================================================
    # 助手会话入口
    # =========================================================================
    def run_assistant_session(self, payload: dict, active_context, reader=None) -> list[dict[str, Any]] | dict[str, Any] | list[Any]:
        """运行通用助手会话。"""
        return self.assistant_runtime.run_session(payload, active_context, reader)

    def estimate_assistant_session_request(self, payload: dict, active_context, reader=None) -> dict[str, Any]:
        """估算助手主对话输入的请求消耗。"""
        return self.assistant_runtime.estimate_session_request(payload, active_context, reader)

    # =========================================================================
    # 会话取消控制
    # =========================================================================
    def cancel_assistant_request(self, session_id: str) -> bool:
        """标记某个助手会话为已取消。"""
        return self.assistant_runtime.cancel_session(session_id)


class AITaskRequestCancelled(Exception):
    """用户主动取消的 AI 异步任务请求"""
    pass
    
