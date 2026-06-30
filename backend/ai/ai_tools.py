"""AI 工具定义与执行模块。

这里同时维护三类内容：
1. 工具入参契约，供 schema 生成与运行时校验复用
2. 工具静态元数据，供模型理解和前端展示复用
3. 工具执行器，把具体业务查询封装成统一结果协议
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from backend.database.dao import ModDAO, GroupDAO
from backend.load_order.package_tokens import parse_package_token
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileContext
from backend.managers.mgr_game_logs import LogCondenser
from backend.settings import DATA_DIR
from backend.utils.logger import logger
from backend.utils.tools import clean_rich_text_for_ai, normalize_package_id, normalize_string_list, normalize_text


class ToolArgsModel(BaseModel):
    """AI 工具参数模型基类。

    约束统一放在这里，原因：
    - 让 schema 生成和运行时校验共用同一份定义
    - 明确禁止额外字段，减少模型“编参数”带来的脏数据
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ToolArgsT = TypeVar("ToolArgsT", bound=ToolArgsModel)

AI_MOD_INFO_SIMPLE_FIELDS = (
    'package_id',
    'name',
    'workshop_id',
    'supported_versions',
    'is_active',
    'path',
)

AI_MOD_INFO_ALLOWED_FIELDS = (
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


class GetLogContextArgs(ToolArgsModel):
    """日志上下文查询参数。"""

    target_line: int = Field(..., gt=0, description="错误摘要中提供的代表行号 target_line。")
    stack_excerpt_lines: int = Field(
        default=15,
        ge=6,
        le=80,
        description="需要返回的堆栈最大行数，默认 15，最大 80。",
    )


class SearchModsArgs(ToolArgsModel):
    """模组搜索参数。"""

    keyword: str = Field(..., min_length=1, description="搜索关键词，例如 RimFridge 或 Harmony。")
    limit: int = Field(default=10, ge=1, le=50, description="最多返回多少个候选模组。")


class GetActiveModListArgs(ToolArgsModel):
    """当前激活模组列表查询参数。"""

    include_names: bool = Field(default=False, description="是否附带具体名称。")


class GetModInfoArgs(ToolArgsModel):
    """模组元数据查询参数。

    这里把约束前移到模型层，原因：
    - schema 会直接告诉模型 scope 的合法枚举值
    - 运行时不用再在 handler 里重复做字段白名单清洗
    """

    package_id: str = Field(..., min_length=1, description="模组 package_id，全小写，如 ludeon.rimworld。")
    scope: Literal["simple", "all", "specific"] = Field(default="simple", description="信息范围：simple / all / specific。")
    fields: list[str] = Field(default_factory=list, description="scope=specific 时要返回的字段。")

    _allowed_fields = frozenset(AI_MOD_INFO_ALLOWED_FIELDS)

    @field_validator("package_id")
    @classmethod
    def _normalize_package_id(cls, value: str) -> str:
        return normalize_package_id(value)

    @field_validator("fields")
    @classmethod
    def _normalize_fields(cls, values: list[str]) -> list[str]:
        return normalize_string_list(values)

    @model_validator(mode="after")
    def _validate_scope_and_fields(self):
        # specific 模式必须显式提供字段，且字段必须来自后端白名单。
        if self.scope != "specific": return self
        if not self.fields:
            raise ValueError("scope=specific 时必须提供至少一个字段")
        invalid_fields = [field for field in self.fields if field not in self._allowed_fields]
        if invalid_fields:
            raise ValueError(f"fields 含不支持字段: {invalid_fields}")
        return self


class GetModRulesArgs(ToolArgsModel):
    """模组规则查询参数。"""

    package_id: str = Field(..., min_length=1)
    native_only: bool = Field(
        default=False,
        description="true=仅返回作者原生规则；false=返回管理器合并后的最终生效规则。",
    )


class GetModUserDataArgs(ToolArgsModel):
    """模组用户态补充信息查询参数。"""

    package_id: str = Field(..., min_length=1)


class GetGroupModsArgs(ToolArgsModel):
    """分组模组查询参数。"""

    group_name: str = Field(..., min_length=1, max_length=80, description="要查询的分组名，支持模糊匹配。")
    limit: int = Field(default=40, ge=1, le=100, description="每个分组最多返回多少个模组。")

    @field_validator("group_name")
    @classmethod
    def _normalize_group_name(cls, value: str) -> str:
        return normalize_text(value)


@dataclass(frozen=True, slots=True)
class ToolDefinition(Generic[ToolArgsT]):
    """单个工具的静态定义。

    它是工具层的单一真相源：
    - `args_model` 生成参数 schema
    - `llm_description` 给模型理解工具语义
    - `ui_description` 给前端展示用途与边界
    - `result_summarizer` 负责生成 trace/UI 摘要
    - `handler_name` 声明真正的执行入口

    这样工具的可变元数据不会散落在 runtime / prompt / UI 三处。
    """

    name: str
    label: str
    llm_description: str
    ui_description: str
    args_model: type[ToolArgsT]
    handler_name: str
    result_summarizer: Callable[[Any], str] | None = None

    def bind(self, handler: Callable[[ToolArgsT], Any]) -> "ToolSpec[ToolArgsT]":
        """把静态定义与具体处理函数绑定成可执行规范对象。"""
        return ToolSpec(definition=self, handler=handler)

    def to_frontend_definition(self) -> dict[str, Any]:
        """导出前端工具面板可直接消费的定义。"""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "id": self.name,
            "label": self.label or self.name,
            "description": self.ui_description,
            "parameters": schema,
        }


@dataclass(frozen=True, slots=True)
class ToolSpec(Generic[ToolArgsT]):
    """单个工具的运行时规范对象。"""

    definition: ToolDefinition[ToolArgsT]
    handler: Callable[[ToolArgsT], Any]

    def to_openai_schema(self) -> dict[str, Any]:
        """导出 OpenAI/LiteLLM 可直接消费的 function schema。"""
        schema = self.definition.args_model.model_json_schema()
        # title 对模型帮助不大，去掉可略微减小请求体体积。
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.definition.name,
                "description": self.definition.llm_description,
                "parameters": schema,
            },
        }


@dataclass(slots=True)
class ToolExecutionResult:
    """单次工具执行的标准结果。

    设计原则：
    - `model_output` 继续保留给模型消费的字符串视图，兼容现有 tool message 协议
    - `data` 提供结构化结果，供 runtime 记录证据、记忆和 trace
    - `summary` 提供面向 UI/trace 的简短说明，避免调用方再二次解析 JSON
    """

    name: str
    ok: bool
    model_output: str
    data: Any = None
    summary: str = ""
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _default_result_summary(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    return ""


def _summarize_log_context(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    if isinstance(payload, dict):
        line_no = payload.get("representative_line")
        if line_no: return f"已返回代表行 #{line_no} 的日志上下文"
    return "已返回目标日志的上下文"


def _summarize_search_mods(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    if isinstance(payload, dict):
        return f"已找到 {len(payload.get('matched', []) or [])} 个候选模组"
    return ""


def _summarize_active_mods(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    if isinstance(payload, dict):
        return f"已返回 {payload.get('total_active', 0)} 个激活模组"
    return ""


def _summarize_mod_info(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    if isinstance(payload, dict):
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        return f"已返回模组元数据：{data.get('name') or payload.get('package_id') or '未知模组'}"
    return ""


def _summarize_mod_rules(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    return "已返回模组规则信息"


def _summarize_mod_user_data(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    return "已返回模组的用户备注/标签/分组信息"


def _summarize_group_mods(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return f"执行失败：{payload['error']}"
    if isinstance(payload, dict):
        return f"已返回 {len(payload.get('matched_groups', []) or [])} 个匹配分组"
    return ""


TOOL_DEFINITIONS: dict[str, ToolDefinition[Any]] = {
    "get_log_context": ToolDefinition(
        name="get_log_context",
        label="日志上下文",
        llm_description="读取某条错误摘要对应的详细日志上下文，包含原始报错内容与截断堆栈。仅当摘要不足以定位问题时再调用。",
        ui_description="获取指定错误日志的详细上下文（包含完整错误信息和核心堆栈）。仅当摘要中的 stack_preview 无法让你得出结论时才使用。",
        args_model=GetLogContextArgs,
        handler_name="_tool_get_log_context",
        result_summarizer=_summarize_log_context,
    ),
    "search_mods": ToolDefinition(
        name="search_mods",
        label="搜索模组",
        llm_description="按名称、别名、作者或 package_id 片段搜索可能对应的模组，用于确认准确 package_id。",
        ui_description="当且仅当你不确定某个 Mod 的准确 package_id 时，使用此工具模糊搜索。可输入名字、别名或部分 ID 查找可能对应的 package_id。",
        args_model=SearchModsArgs,
        handler_name="_tool_search_mods",
        result_summarizer=_summarize_search_mods,
    ),
    "get_active_mod_list": ToolDefinition(
        name="get_active_mod_list",
        label="当前启用列表",
        llm_description="获取当前环境中的启用模组列表，用于整体排序和冲突排查。",
        ui_description="获取当前排序文件中的已激活模组列表，用于宏观检查模组顺序，返回模组包名列表。",
        args_model=GetActiveModListArgs,
        handler_name="_tool_get_active_mod_list",
        result_summarizer=_summarize_active_mods,
    ),
    "get_mod_info": ToolDefinition(
        name="get_mod_info",
        label="模组元数据",
        llm_description=f"读取已安装模组的元数据。simple 返回基本信息：{AI_MOD_INFO_SIMPLE_FIELDS}；all 返回全部信息；specific 返回指定字段：{AI_MOD_INFO_ALLOWED_FIELDS}。",
        ui_description=f"获取当前环境中已安装模组的元数据。simple 返回基本必要信息：{AI_MOD_INFO_SIMPLE_FIELDS}。all 返回全部信息；specific 返回可选字段信息：{AI_MOD_INFO_ALLOWED_FIELDS}。",
        args_model=GetModInfoArgs,
        handler_name="_tool_get_mod_info",
        result_summarizer=_summarize_mod_info,
    ),
    "get_mod_rules": ToolDefinition(
        name="get_mod_rules",
        label="模组规则",
        llm_description="读取模组依赖、前置、后置和不兼容规则，用于判断显性排序和兼容关系。",
        ui_description="获取该模组的依赖模组、前置/后置模组和不兼容模组规则，以了解该模组与其它模组之间的显性关系。只有在怀疑缺失前置、加载顺序错误或存在不兼容模组时再调用。",
        args_model=GetModRulesArgs,
        handler_name="_tool_get_mod_rules",
        result_summarizer=_summarize_mod_rules,
    ),
    "get_mod_user_data": ToolDefinition(
        name="get_mod_user_data",
        label="模组用户数据",
        llm_description="读取管理器中的模组别名、标签、备注、颜色、分组等用户态信息，仅用于辅助理解玩家归类。",
        ui_description="获取该已安装模组在管理器中的用户态上下文：别名、标签、备注、颜色、自定义类型和所属分组。这些信息只用于辅助理解玩家归类，属于模组管理器专有信息，与游戏机制无关。",
        args_model=GetModUserDataArgs,
        handler_name="_tool_get_mod_user_data",
        result_summarizer=_summarize_mod_user_data,
    ),
    "get_group_mods": ToolDefinition(
        name="get_group_mods",
        label="分组模组",
        llm_description="按分组名读取分组下的模组列表，仅用于辅助理解玩家自己的分组归类。",
        ui_description="按分组名查询分组所含模组。分组信息只用于辅助理解玩家归类，属于模组管理器专有信息，与游戏机制无关。",
        args_model=GetGroupModsArgs,
        handler_name="_tool_get_group_mods",
        result_summarizer=_summarize_group_mods,
    ),
}


def get_tool_definitions() -> dict[str, dict[str, Any]]:
    """返回给前端展示用的工具定义。"""
    definitions: dict[str, dict[str, Any]] = {}
    for name, definition in TOOL_DEFINITIONS.items():
        definitions[name] = definition.to_frontend_definition()
    return definitions

class AIToolExecutor:
    """
    AI 工具执行器 (注册表模式)
    一次定义工具的 AI 描述、参数结构和执行方法。
    """
    
    def __init__(self, active_context: ProfileContext|None, payload: dict, reader):
        self.context = active_context
        self.payload = dict(payload or {})
        self.request_payload = self._extract_request_payload(self.payload)
        self.reader = reader
        self.log_source_type, self.log_filename = self._resolve_log_context()
        
        # 预加载：缓存一份当前已激活的 Mod ID 集合，供各个工具复用
        self._active_mod_ids_set = self._get_active_mod_id_set()

        # 工具注册表只保留一份“规范对象”，由它同时驱动 schema 生成和入参校验。
        self.registry: dict[str, ToolSpec[Any]] = {
            name: definition.bind(getattr(self, definition.handler_name))
            for name, definition in TOOL_DEFINITIONS.items()
        }

    # =====================================================================
    # 外部接口：供 AIManager 调用
    # =====================================================================

    def get_tool_schemas(self, enabled_names: list[str] | None = None) -> list[dict[str, Any]]:
        """
        动态生成大模型所需的 OpenAI/LiteLLM 标准 JSON Schema 结构。
        :param enabled_names: 前端传来的启用工具名称列表，如果为空则返回全部
        """
        schemas = []
        enabled_names = enabled_names or []
        for name, spec in self.registry.items():
            # 过滤未启用的工具
            if enabled_names and name not in enabled_names: continue
            schemas.append(spec.to_openai_schema())
        return schemas

    def execute_structured(self, name: str, arguments_str: str) -> ToolExecutionResult:
        """
        统一的工具执行路由。

        流程固定为：
        1. 解析模型给出的 JSON 参数
        2. 用 `pydantic` 做强校验和规范化
        3. 把“干净参数对象”交给具体工具方法

        这样具体工具方法可以专注业务，不必反复写 `get()/int()/try/except` 样板代码。
        """
        try:
            args = json.loads(arguments_str) if arguments_str else {}
        except json.JSONDecodeError:
            payload = {"error": "参数解析失败(Invalid JSON)"}
            return self._build_execution_result(name=name, payload=payload)

        spec = self.registry.get(name)
        if spec is None:
            payload = {"error": f"系统未注册此工具: {name}"}
            return self._build_execution_result(name=name, payload=payload)

        try:
            validated_args = spec.definition.args_model.model_validate(args)
        except ValidationError as e:
            logger.warning(
                "[AI诊断] 工具参数校验失败。tool=%s",
                name,
                extra={"error_code": "AI.TOOL.ARGS_INVALID", "extra_context": {"tool": name, "original_error": str(e)}},
            )
            payload = {"error": f"工具参数不合法: {e.errors(include_url=False)}"}
            return self._build_execution_result(name=name, payload=payload)

        try:
            logger.debug(f"[AI诊断] 开始执行工具 name={name} args={validated_args.model_dump()}")
            payload = spec.handler(validated_args)
            return self._build_execution_result(name=name, payload=payload)
        except Exception as e:
            logger.error(
                "AI 工具执行异常。tool=%s",
                name,
                extra={"error_code": "AI.TOOL.EXECUTION_FAILED", "extra_context": {"tool": name, "original_error": str(e)}},
                exc_info=True,
            )
            payload = {"error": f"工具执行内部异常: {str(e)}"}
            return self._build_execution_result(name=name, payload=payload)

    def execute(self, name: str, arguments_str: str) -> str:
        """兼容旧调用方：继续返回模型可读字符串。"""
        return self.execute_structured(name, arguments_str).model_output

    def _build_execution_result(self, *, name: str, payload: Any) -> ToolExecutionResult:
        normalized_payload = self._normalize_tool_payload(payload)
        error_text = ""
        ok = True
        if isinstance(normalized_payload, dict) and normalized_payload.get("error"):
            ok = False
            error_text = str(normalized_payload.get("error") or "").strip()
        return ToolExecutionResult(
            name=name,
            ok=ok,
            model_output=self._stringify_tool_payload(normalized_payload),
            data=normalized_payload,
            summary=self._summarize_tool_payload(name, normalized_payload),
            error=error_text,
        )

    def _normalize_tool_payload(self, payload: Any) -> Any:
        if isinstance(payload, BaseModel):
            return payload.model_dump()
        return payload

    def _stringify_tool_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        try:
            return json.dumps(payload, ensure_ascii=False)
        except TypeError:
            return json.dumps({"result": str(payload)}, ensure_ascii=False)

    def _summarize_tool_payload(self, name: str, payload: Any) -> str:
        try:
            spec = self.registry.get(name)
            if spec and spec.definition.result_summarizer:
                summary = str(spec.definition.result_summarizer(payload) or "").strip()
                if summary: return summary
        except Exception:
            pass

        safe_text = self._stringify_tool_payload(payload).replace("\r", " ").replace("\n", " ").strip()
        if not safe_text: return "工具执行完成，但没有返回可展示内容"
        return safe_text[:180] + ("..." if len(safe_text) > 180 else "")

    def get_tool_display_name(self, name: str) -> str:
        """返回工具在 trace / UI 中应该展示的稳定名称。"""
        spec = self.registry.get(name)
        if spec: return str(spec.definition.label or name or "系统工具").strip() or "系统工具"
        definition = TOOL_DEFINITIONS.get(name)
        if definition: return str(definition.label or name or "系统工具").strip() or "系统工具"
        return str(name or "系统工具").strip() or "系统工具"

    def build_tool_call_display(self, name: str, arguments_str: str) -> dict[str, str]:
        """把工具调用参数整理成适合前端展示的摘要视图。"""
        parsed_args = self._parse_tool_arguments(arguments_str)
        return {
            "display_name": self.get_tool_display_name(name),
            "arguments_preview": self._build_arguments_preview(parsed_args),
            "arguments_pretty": self._pretty_tool_value(parsed_args if parsed_args is not None else arguments_str),
        }

    def build_tool_result_display(self, result: ToolExecutionResult) -> dict[str, str]:
        """把工具执行结果整理成适合前端展示的摘要视图。"""
        return {
            "display_name": self.get_tool_display_name(result.name),
            "result_pretty": self._pretty_tool_value(result.data if result.data is not None else result.model_output),
        }

    def _parse_tool_arguments(self, arguments_str: str) -> dict[str, Any] | None:
        if not arguments_str: return {}
        try:
            parsed = json.loads(arguments_str)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    def _build_arguments_preview(self, args: dict[str, Any] | None) -> str:
        if not args: return ""
        preview_parts: list[str] = []
        for key, value in list(args.items())[:2]:
            if value is None:
                continue
            text = self._summarize_argument_value(value)
            if not text:
                continue
            preview_parts.append(f"{key}={text}")
        return ", ".join(preview_parts)

    def _summarize_argument_value(self, value: Any) -> str:
        if isinstance(value, list):
            compact = ",".join(str(item) for item in value[:3])
            if len(value) > 3:
                compact += ",..."
            return compact
        if isinstance(value, dict):
            compact = json.dumps(value, ensure_ascii=False)
            return compact[:48] + ("..." if len(compact) > 48 else "")
        text = str(value).strip()
        return text[:48] + ("..." if len(text) > 48 else "")

    def _pretty_tool_value(self, value: Any) -> str:
        if value is None or value == "": return "暂无结果"
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return value
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return str(value)

    def _extract_request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        assistant_context = dict(payload.get("assistant_context") or {})
        return dict(assistant_context.get("request_payload") or payload.get("request_payload") or {})

    def _resolve_log_context(self) -> tuple[str, str]:
        """统一解析日志工具所需的 source_type / filename。

        优先级：
        1. assistant_context.request_payload
        2. 顶层已标准化的运行时 payload
        3. diagnosis_context 附件 source
        """

        source_type = str(
            self.request_payload.get("source_type")
            or self.request_payload.get("log_source_type")
            or self.payload.get("log_source_type")
            or ""
        ).strip()
        filename = str(
            self.request_payload.get("filename")
            or self.payload.get("filename")
            or ""
        ).strip()

        attachments = self.request_payload.get("attachments", []) or self.payload.get("attachments", []) or []
        if not isinstance(attachments, list):
            attachments = []

        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            if str(attachment.get("kind") or "").strip() != "diagnosis_context":
                continue
            source = dict(attachment.get("source") or {})
            source_type = source_type or str(source.get("source_type") or "").strip()
            filename = filename or str(source.get("filename") or "").strip()
            if source_type and filename:
                break

        return source_type, filename

    # =====================================================================
    # 具体的工具实现方法 (Methods)
    # =====================================================================
    
    def _get_active_mod_id_set(self) -> set:
        """辅助方法：返回当前启用列表中的 package_id 集合"""
        if not self.context: return set()
        lo_mgr = LoadOrderManager(self.context)
        return {
            token_info.canonical_package_id
            for pid in lo_mgr.read_active_mods().get('active_mods', [])
            for token_info in [parse_package_token(pid)]
            if token_info.canonical_package_id
        }

    def _tool_get_log_context(self, args: GetLogContextArgs) -> dict[str, Any]:
        """获取指定行号的日志上下文，包含完整调用栈。"""
        target_line = args.target_line
        # 这里再夹一层保护，目的是即使未来放宽 schema，也保证业务上限不变。
        stack_excerpt_lines = max(6, min(args.stack_excerpt_lines, 80))

        # 3. 获取文件路径和 reader
        source_type = self.log_source_type or "game"
        filename = self.log_filename
        if not filename: return {"error": "当前会话缺少日志文件上下文，无法执行日志定位工具。"}
        if source_type == 'game':
            if self.reader and hasattr(self.reader, "resolve_log_file_path"):
                filepath = self.reader.resolve_log_file_path(filename)
            else:
                filepath = os.path.join(self.context.user_data_path, filename) if self.context else ""
        else:
            filepath = os.path.join(DATA_DIR, 'logs', filename)
        if not os.path.exists(filepath):
            return {"error": f"找不到对应日志文件: {filename}"}
        if not self.reader or not hasattr(self.reader, "get_raw_logs_by_lines"):
            return {"error": "当前日志读取器不支持按行反查日志块"}

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
            return {"error": f"无法定位请求的代表行号 #{target_line}。该错误可能已被折叠或文件已变更。"}
        
        # 6. 提炼极其纯净的上下文给 AI，绝对不暴露 raw_lines 数组等让它困惑的数据
        level = str(target_block.get("level") or "UNKNOWN")
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
        return result_payload

    def _tool_get_active_mod_list(self, args: GetActiveModListArgs) -> dict[str, Any]:
        """获取当前激活的模组列表，可选择是否包含模组名称。"""
        include_names = args.include_names
        if not self.context: return {"error": "缺少当前环境上下文，无法执行工具。"}
        lo_mgr = LoadOrderManager(self.context)
        mods_data = lo_mgr.read_active_mods().get('mods', [])
        if include_names:
            active_list = {m.get('package_id', ''): m.get('name', '') for m in mods_data}
        else:
            active_list = [m.get('package_id', '') for m in mods_data]
        return {"total_active": len(mods_data), "active_order": active_list}

    def _tool_search_mods(self, args: SearchModsArgs) -> dict[str, Any]:
        """
        根据关键词搜索可见的模组，返回匹配结果。
        匹配范围：package_id / workshop_id / name / alias_name / author
        """
        keyword = args.keyword
        if not keyword: return {"error": "必须提供 keyword"}
        needle = str(keyword or '').strip().lower()
        if not needle: return {"keyword": keyword, "matched": []}
        active_ids = self._active_mod_ids_set
        limit = args.limit
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
        
        return {"keyword": keyword, "matched": trimmed}

    def _tool_get_mod_info(self, args: GetModInfoArgs) -> dict[str, Any]:
        """获取指定模组的详细信息，可选择返回范围和字段。"""
        pkg_id = args.package_id.lower()
        if not pkg_id: return {"error": "必须提供有效的 package_id"}
        mod = ModDAO.get_visible_profile_mod(self.context, pkg_id)
        if not mod: return {"error": f"当前环境中未找到此模组: {pkg_id}"}
        scope = args.scope
        fields = args.fields
        # 1. 初始化安全的返回数据结构
        safe_mod = {}
        for field_name in AI_MOD_INFO_ALLOWED_FIELDS:
            value = mod.get(field_name)
            if field_name == 'description':
                value = clean_rich_text_for_ai(value, max_length=1000)
            elif field_name == 'is_active':
                value = pkg_id in self._active_mod_ids_set
            safe_mod[field_name] = value
        # 3. 根据 scope 处理字段选择
        if scope == 'all':
            selected_fields = list(AI_MOD_INFO_ALLOWED_FIELDS)
            invalid_fields = []
        elif scope == 'specific':
            selected_fields = [field_name for field_name in fields if field_name in AI_MOD_INFO_ALLOWED_FIELDS]
            invalid_fields = []
        else:
            selected_fields = list(AI_MOD_INFO_SIMPLE_FIELDS)
            invalid_fields = []

        data = {field_name: safe_mod.get(field_name) for field_name in selected_fields}
        result =  {
            "package_id": pkg_id,
            "scope": scope,
            "returned_fields": selected_fields,
            "invalid_fields": invalid_fields,
            "data": data,
        }
        return result

    def _tool_get_mod_rules(self, args: GetModRulesArgs) -> dict[str, Any]:
        """获取指定模组的生效规则，可选择是否仅返回原生规则。"""
        pkg_id = args.package_id.lower()
        native_only = args.native_only
        if not self.context: return {"error": "缺少当前环境上下文，无法执行工具。"}
        mod = ModDAO.get_visible_profile_mod(self.context, pkg_id)
        if not mod: return {"error": f"未找到此模组: {pkg_id}"}
        if native_only:
            return {
                "dependencies": mod.get("dependencies_mods", []),
                "load_after": mod.get("load_after_mods", []),
                "load_before": mod.get("load_before_mods", []),
                "incompatible": mod.get("incompatible_mods", [])
            }
        else:
            # 获取经过管理器合并后的真实生效规则
            from backend.managers.mgr_rules import RuleManager
            effective_rules = RuleManager(self.context).get_effective_mod_rules(pkg_id, mod)
            return effective_rules

    def _tool_get_mod_user_data(self, args: GetModUserDataArgs) -> dict[str, Any]:
        """获取指定模组的用户自定义信息，。"""
        pkg_id = args.package_id.lower()
        if not pkg_id: return {"error": "必须提供有效的 package_id"}
        mod = ModDAO.get_visible_profile_mod(self.context, pkg_id)
        if not mod: return {"error": f"当前环境中未找到此模组: {pkg_id}"}
        result = {
            "package_id": pkg_id,
            "alias_name": mod.get("alias_name", mod.get("name")),
            "tags": mod.get("tags", []),
            "groups": mod.get("groups", []),
            "notes": str(mod.get("notes") or "").strip() or None,
            "sign_color": mod.get("sign_color"),
            "mod_type": mod.get("user_mod_type", mod.get("mod_type")),
        }
        
        return result

    def _tool_get_group_mods(self, args: GetGroupModsArgs) -> dict[str, Any]:
        """获取指定分组的模组列表，可选择返回范围和字段。"""
        group_name = args.group_name.strip()
        if not group_name: return {"error": "必须提供有效的 group_name"}
        limit = args.limit
        visible_mods = ModDAO.get_profile_mods(self.context)
        active_ids = self._active_mod_ids_set
        visible_map = {
            str(mod.get('package_id') or '').strip().lower(): mod
            for mod in visible_mods
            if str(mod.get('package_id') or '').strip()
        }
        if not visible_map: return {"matched_groups": []}
        
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
        return result
    


