"""AI 领域层契约。

这里放“轻量但稳定”的共享结构，避免把这些定义继续塞回 `AIManager`：
1. `AssistantDefinition` / `TaskDefinition` 描述系统固定入口
2. `AIOutputModel` 描述需要结构化校验的模型输出
3. `AttachmentDraft` / `ResolvedContextAttachment` 描述附件上下文协议
4. `RequestTraceRecord` 描述运行期内存态的调用链记录
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from backend.utils.tools import (
    normalize_package_id,
    normalize_package_ids,
    normalize_string_list,
    normalize_text,
)


class AssistantDefinition(BaseModel):
    """助手定义。

    这是统一助手框架里的核心配置对象：
    - `prompt_id` 决定该助手默认强化方向
    - `tool_scope_selectable` 决定该助手运行期最多允许使用哪些工具

    设计上故意不把运行期消息、trace、reader 等动态对象塞进来，
    让它保持成可序列化、可持久化、易管理的静态配置。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str
    name: str
    description: str = ""
    prompt_id: str
    enabled: bool = True
    is_system: bool = True
    source_kinds: list[str] = Field(default_factory=list)
    session_mode: Literal["multi_turn"] = "multi_turn"
    tool_scope_selectable: list[str] = Field(default_factory=list)
    action_types: list[str] = Field(default_factory=list)

    @field_validator("tool_scope_selectable", "source_kinds", "action_types")
    @classmethod
    def _normalize_string_list(cls, values: list[str]) -> list[str]:
        return normalize_string_list(values)


class TaskDefinition(BaseModel):
    """单次任务定义。

    任务入口和助手入口一样，属于系统固定的“运行协议层”：
    - 任务本身决定调用方式、输入来源和返回结构
    - Prompt 只决定同一任务该如何表达

    因此这里不允许用户新增任意任务类型，只允许为既有任务入口切换绑定 Prompt。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str
    name: str
    description: str = ""
    prompt_id: str
    enabled: bool = True
    is_system: bool = True
    source_kinds: list[str] = Field(default_factory=list)
    session_mode: Literal["single_turn"] = "single_turn"

    @field_validator("source_kinds")
    @classmethod
    def _normalize_source_kinds(cls, values: list[str]) -> list[str]:
        return normalize_string_list(values)


class PromptVariableDefinition(BaseModel):
    """Prompt 编辑器里可插入的变量定义。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    key: str
    label: str
    description: str = ""
    required_fields: list[str] = Field(default_factory=list)

    @field_validator("required_fields")
    @classmethod
    def _normalize_required_fields(cls, values: list[str]) -> list[str]:
        return normalize_string_list(values)


class AttachmentProjectionFieldDefinition(BaseModel):
    """附件字段剪裁元数据。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    path: str
    label: str
    description: str = ""
    default_enabled: bool = True


class PromptCategoryDefinition(BaseModel):
    """Prompt 分类定义。

    Prompt 的分类只描述“它服务于哪类入口”，
    不再决定会话模式；多轮/单轮由助手或任务入口自身决定。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: Literal["assistant", "task"]
    label: str
    description: str = ""
    base_variables: list[PromptVariableDefinition] = Field(default_factory=list)


class AttachmentDefinition(BaseModel):
    """系统级附件定义。

    用户只能为 Prompt 选择系统已注册的附件类型；
    附件的真实结构、补齐逻辑、可暴露字段和摘要生成方式全部由后端统一维护。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    kind: str
    label: str
    description: str = ""
    allowed_owner_types: list[str] = Field(default_factory=list)
    required_source_keys: list[str] = Field(default_factory=list)
    selector_modes: list[str] = Field(default_factory=list)
    required_selector_keys: list[str] = Field(default_factory=list)
    prompt_variables: list[PromptVariableDefinition] = Field(default_factory=list)
    projection_fields: list[str] = Field(default_factory=list)
    default_projection: list[str] = Field(default_factory=list)
    projection_options: list[AttachmentProjectionFieldDefinition] = Field(default_factory=list)

    @field_validator("allowed_owner_types", "required_source_keys", "selector_modes", "required_selector_keys", "projection_fields", "default_projection")
    @classmethod
    def _normalize_string_list(cls, values: list[str]) -> list[str]:
        return normalize_string_list(values)


class ActionDefinition(BaseModel):
    """系统注册的动作定义。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: str
    label: str
    description: str = ""
    payload_schema: dict[str, Any] = Field(default_factory=dict)
    preview_template: str = ""
    execute_label: str = ""
    unsupported_message: str = ""
    execution_failed_message: str = ""
    render_config: dict[str, Any] = Field(default_factory=dict)
    execution_config: dict[str, Any] = Field(default_factory=dict)
    variants: dict[str, "ActionVariantDefinition"] = Field(default_factory=dict)


class ActionVariantDefinition(BaseModel):
    """动作变体定义。

    同一种动作类型可能存在多个 `variant`，例如：
    - `MOD_STATE.enable`
    - `MOD_STATE.disable`

    这些差异应放在后端元数据里，由前端统一按定义渲染，
    而不是在组件里分支硬编码标题、描述、预览和交互提示。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    label: str
    title: str = ""
    description: str = ""
    preview_template: str = ""
    render_config: dict[str, Any] = Field(default_factory=dict)
    execute_label: str = ""
    missing_payload_message: str = ""
    blocked_message: str = ""
    success_message: str = ""
    confirm_title: str = ""
    confirm_message: str = ""
    confirm_confirm_text: str = ""
    post_success_title: str = ""
    post_success_message: str = ""
    post_success_confirm_text: str = ""


ActionDefinition.model_rebuild()


class AttachmentDraft(BaseModel):
    """前端发来的轻量附件草稿。

    默认策略是：
    - 前端传轻引用，保留即时 UI 选择态
    - 后端按 `kind + source + selector` 补齐为权威上下文
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    kind: str = ""
    source: dict[str, Any] = Field(default_factory=dict)
    selector: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _normalize_kind(cls, value: str) -> str:
        return normalize_text(value)


class ResolvedContextAttachment(BaseModel):
    """后端补齐后，真正送给模型消费的标准化附件。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: str
    title: str = ""
    summary: str = ""
    facts: dict[str, Any] = Field(default_factory=dict)
    token_estimate: int = 0


class RequestToolCallTrace(BaseModel):
    """单个工具调用的 trace。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    tool_id: str = ""
    name: str
    arguments: str = ""
    status: Literal["running", "done", "error"] = "done"
    result: str = ""
    duration_ms: int | None = None
    summary: str = ""
    display_name: str = ""
    arguments_preview: str = ""
    arguments_pretty: str = ""
    result_pretty: str = ""


class RequestTraceTokenUsage(BaseModel):
    """单轮请求的 token 统计。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tool_rounds: int = 0
    answer_completion_tokens: int = 0
    reasoning_completion_tokens: int = 0
    tool_call_completion_tokens: int = 0


class MessageTokenUsage(BaseModel):
    """单条可见消息对应的请求级 token 估算。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RequestMessageUsage(BaseModel):
    """单轮请求中的用户/助手消息 token 估算。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    user: MessageTokenUsage = Field(default_factory=MessageTokenUsage)
    assistant: MessageTokenUsage = Field(default_factory=MessageTokenUsage)


class PromptInputBreakdown(BaseModel):
    """主对话输入的细分统计。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    total_tokens: int = 0
    prompt_template_tokens: int = 0
    memory_tokens: int = 0
    attachment_tokens: int = 0
    user_input_tokens: int = 0
    tool_context_tokens: int = 0
    forced_summary_tokens: int = 0


class RequestTraceRecord(BaseModel):
    """运行期内存态的调用链记录。

    当前只保留在内存里，方便调试与分析问题；
    但结构设计为可序列化，后续需要落盘时可直接复用。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    trace_id: str
    session_id: str
    assistant_id: str = ""
    owner_type: str = ""
    owner_key: str = ""
    prompt_id: str = ""
    model: str = ""
    started_at: int
    finished_at: int | None = None
    status: str = "running"
    user_input_text: str = ""
    messages_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)
    raw_attachments: list[dict[str, Any]] = Field(default_factory=list)
    resolved_attachments: list[ResolvedContextAttachment] = Field(default_factory=list)
    tool_calls: list[RequestToolCallTrace] = Field(default_factory=list)
    final_output: str = ""
    final_reasoning: str = ""
    token_usage: RequestTraceTokenUsage = Field(default_factory=RequestTraceTokenUsage)
    message_usage: RequestMessageUsage = Field(default_factory=RequestMessageUsage)
    prompt_input_breakdown: PromptInputBreakdown = Field(default_factory=PromptInputBreakdown)
    error: str = ""


class AIOutputModel(BaseModel):
    """结构化输出的公共基类。

    输出校验以“尽量兼容”为目标：
    - 忽略模型偶尔附带的额外字段
    - 保留调用方现有的文本兜底能力
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class ModAliasGenerationItem(AIOutputModel):
    """模组别名/备注生成的单条结果。"""

    package_id: str
    alias_name: str = ""
    notes: str = ""

    @field_validator("package_id", mode="before")
    @classmethod
    def _normalize_package_id(cls, value: str) -> str:
        return normalize_package_id(value)

    @field_validator("alias_name", "notes", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: str) -> str:
        return normalize_text(value)


class AIActionPayload(AIOutputModel):
    """AI 动作 payload 基类。

    当前动作类型的 payload 结构并不完全统一，因此先保留宽松对象模型，
    避免因为某一类动作字段未枚举导致整个解析失败。
    """


class TextTransferPayload(AIActionPayload):
    """文本转移动作。"""

    text: str

    @field_validator("text")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        return normalize_text(value)


class SettingUpdatePayload(AIActionPayload):
    """设置更新动作。"""

    setting_key: str
    value: Any = None

    @field_validator("setting_key")
    @classmethod
    def _normalize_setting_key(cls, value: str) -> str:
        return normalize_text(value)


class ModStatePayload(AIActionPayload):
    """模组启用态动作。

    统一对外只暴露 `mod_ids`。
    """

    mod_ids: list[str] = Field(default_factory=list)

    @field_validator("mod_ids", mode="before")
    @classmethod
    def _normalize_mod_ids(cls, value):
        raw_values = value if isinstance(value, list) else [value]
        return normalize_package_ids(raw_values)


class ModRulePayload(AIActionPayload):
    """模组规则动作。"""

    mod_id: str
    rule_type: Literal["loadAfter", "loadBefore", "incompatibleWith"]
    target_id: str

    @field_validator("mod_id", "target_id")
    @classmethod
    def _normalize_mod_id(cls, value: str) -> str:
        return normalize_package_id(value)

    @field_validator("rule_type", mode="before")
    @classmethod
    def _normalize_rule_type(cls, value: str) -> str:
        normalized = str(value or "").strip()
        alias_map = {
            "loadAfter": "loadAfter",
            "loadBefore": "loadBefore",
            "incompatibleWith": "incompatibleWith",
        }
        return alias_map.get(normalized, normalized)


class AIAction(AIOutputModel):
    """前端可执行动作。"""

    type: Literal["MOD_STATE", "MOD_RULE", "TEXT_TRANSFER", "SETTING_UPDATE"]
    variant: str
    # 这里允许模型省略 title/description，再由后置归一化补默认值。
    # 原因：
    # - 一些国产模型在结构化输出时经常只稳定产出 type/payload
    # - 如果这里仍要求必填，会在进入归一化逻辑前直接校验失败
    # - 因此先放宽入口，再由后端统一补成前端可展示的稳定文案
    title: str = ""
    description: str = ""
    # payload 结构按动作类型变化较大，因此保留宽松对象；
    # 但至少要求它必须是对象，避免模型塞入字符串/数组污染前端执行层。
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_payload_and_text(self):
        # 这里只做结构归一化，不注入任何展示文案。
        # 标题/描述属于 UI 层职责，避免契约层掺入中文硬编码。
        self.title = str(self.title or "").strip()
        self.description = str(self.description or "").strip()
        self.variant = str(self.variant or "").strip()

        if self.type == "MOD_STATE":
            if self.variant not in {"enable", "disable"}:
                raise ValueError(f"unsupported MOD_STATE variant: {self.variant or '<empty>'}")
            payload = ModStatePayload.model_validate(self.payload or {})
            self.payload = payload.model_dump()
            return self

        if self.type == "MOD_RULE":
            if self.variant not in {"loadAfter", "loadBefore", "incompatibleWith"}:
                raise ValueError(f"unsupported MOD_RULE variant: {self.variant or '<empty>'}")
            payload = ModRulePayload.model_validate({
                **dict(self.payload or {}),
                "rule_type": self.variant,
            })
            self.payload = payload.model_dump()
            return self

        if self.type == "TEXT_TRANSFER":
            if self.variant not in {"copy_report"}:
                raise ValueError(f"unsupported TEXT_TRANSFER variant: {self.variant or '<empty>'}")
            payload = TextTransferPayload.model_validate({
                "text": (self.payload or {}).get("text") or (self.payload or {}).get("report_text") or "",
            })
            self.payload = payload.model_dump()
            return self

        if self.type == "SETTING_UPDATE":
            if self.variant not in {"set_value"}:
                raise ValueError(f"unsupported SETTING_UPDATE variant: {self.variant or '<empty>'}")
            payload = SettingUpdatePayload.model_validate(self.payload or {})
            self.payload = payload.model_dump()
            return self

        return self


class AIActionsEnvelope(AIOutputModel):
    """动作输出的标准 envelope。"""

    actions: list[AIAction]


class AIAssistantResponseEnvelope(AIOutputModel):
    """assistant 最终输出的统一 envelope。

    设计目标：
    1. 主会话最终只返回一个稳定 JSON 对象
    2. `analysis` 负责用户可见正文
    3. `actions` 负责可执行动作，允许为空数组
    """

    analysis: str = ""
    actions: list[AIAction] = Field(default_factory=list)


class ConversationTraceSession(BaseModel):
    """按会话归档后的链路视图。

    前端会话调试面板需要看的不是“最近 N 条平铺请求”，
    而是某个会话下经历了哪些请求、工具轮与最终输出。
    因此这里补一层按 session 聚合后的投影视图，避免前端自己重复归并。
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    session_id: str
    assistant_id: str = ""
    owner_type: str = ""
    owner_key: str = ""
    title: str = ""
    status: str = "running"
    started_at: int = 0
    finished_at: int | None = None
    trace_count: int = 0
    request_count: int = 0
    total_token_usage: RequestTraceTokenUsage = Field(default_factory=RequestTraceTokenUsage)
    total_message_usage: RequestMessageUsage = Field(default_factory=RequestMessageUsage)
    total_prompt_input_breakdown: PromptInputBreakdown = Field(default_factory=PromptInputBreakdown)
    traces: list[RequestTraceRecord] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
    timeline_items: list[dict[str, Any]] = Field(default_factory=list)
