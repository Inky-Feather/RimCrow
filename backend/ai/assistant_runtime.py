"""通用多轮 assistant 运行时。

这个模块只负责 assistant 的运行协议，不再混入 task/batch 或前端 UI 细节：
1. 解析 assistant 定义与 prompt
2. 解析附件草稿并注入上下文
3. 组装消息、工具与模型参数
4. 执行多轮 tool loop
5. 记录 session trace
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import TypeAdapter, ValidationError

from json_repair import repair_json


from backend.ai.def_actions import normalize_ai_actions
from backend.ai.def_attachments import AttachmentResolver
from backend.ai.ai_contracts import (
    AIAssistantResponseEnvelope,
    AssistantDefinition,
    ConversationTraceSession,
    RequestTraceRecord,
    RequestToolCallTrace,
    ResolvedContextAttachment,
)
from backend.ai.assistant_trace import AssistantTraceStore
from backend.ai.def_output_contracts import (
    build_assistant_output_contract,
    get_allowed_action_types,
)
from backend.ai.ai_tools import AIToolExecutor, ToolExecutionResult
from backend.settings import settings
from backend.utils.constants import get_lang_by_code
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger

ASSISTANT_MAX_LOOPS = 10
TRACE_RECORD_LIMIT = 200
SESSION_RECENT_MESSAGE_LIMIT = 8
SESSION_EVIDENCE_LIMIT = 12
TRACE_TOOL_TIME_SPAN_FALLBACK = 1000

GENERIC_ASSISTANT_SUFFIX_TEMPLATE = (
    "\n\n{tools_description}\n\n"
    "{output_contract}"
)
ASSISTANT_MEMORY_SYSTEM_TEMPLATE = (
    "以下是本会话的后端工作记忆，不是新的用户问题。\n"
    "{memory_summary_block}\n\n"
    "{memory_evidence_block}"
)

DUPLICATE_TOOL_CALL_ERROR = (
    "系统警告：你已经使用完全相同的参数调用过该工具！"
    "请停止重复调用，立即基于已有证据进行分析和总结！"
)
DEFAULT_LOG_ASSISTANT_QUESTION = "请深度分析我提交的日志数据，并给出修复建议。"
DEFAULT_LOG_GLOBAL_SCAN_QUESTION = "请基于本次全局扫描结果直接开始排错，给出最可能的问题根因、证据和修复建议。"
TOOL_UNSUPPORTED_FALLBACK_NOTICE = (
    "系统提示：当前模型或接口不支持原生工具调用。本轮已禁用外部工具，"
    "请不要再尝试调用工具，只基于当前已经提供的上下文给出最终分析。"
)
TOOL_UNSUPPORTED_USER_WARNING = {
    "code": "tools_unsupported",
    "message": "该模型不支持工具调用，无法获取更详细的信息。",
}

def get_prompt_config(prompt_store: dict[str, Any], prompt_id: str) -> dict[str, Any]:
    """读取并复制指定 prompt 配置。"""

    prompt_config = prompt_store.get(prompt_id)
    if not prompt_config:
        raise ValueError(f"Prompt template '{prompt_id}' not found.")
    return dict(prompt_config)


def create_token_usage(model_name: str = "") -> dict[str, Any]:
    """构造统一的 token 统计结构。"""

    return {
        "estimated_prompt_tokens": 0,
        "estimated_completion_tokens": 0,
        "estimated_total_tokens": 0,
        "tool_rounds": 0,
        "estimated_answer_completion_tokens": 0,
        "estimated_reasoning_completion_tokens": 0,
        "estimated_tool_call_completion_tokens": 0,
        "forced_final_round": False,
        "model": model_name,
    }


def create_prompt_input_breakdown() -> dict[str, int]:
    """构造主对话输入的细分统计结构。"""

    return {
        "total_tokens": 0,
        "prompt_template_tokens": 0,
        "memory_tokens": 0,
        "attachment_tokens": 0,
        "user_input_tokens": 0,
        "tool_context_tokens": 0,
        "forced_summary_tokens": 0,
    }


def build_llm_kwargs(llm_gateway, override_config: dict | None = None) -> dict[str, Any]:
    """统一委托网关组装模型调用参数。"""

    return llm_gateway.build_kwargs(override_config)


def safe_format_template(template: str, variables: dict[str, Any]) -> str:
    """安全格式化模板，只替换已提供变量。"""

    double_brace_pattern = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")
    pattern = re.compile(r"\{([A-Za-z0-9_.]+)\}")

    def replace(match):
        """未提供的变量直接置空，避免模板中断整个请求。"""
        key = match.group(1)
        return str(variables.get(key, ""))

    formatted = double_brace_pattern.sub(replace, template)
    return pattern.sub(replace, formatted)


def normalize_message_text(llm_gateway, content: Any) -> str:
    """把运行期消息内容规整成纯文本。"""

    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return llm_gateway._message_text(content)


def estimate_text_tokens(llm_gateway, text: str, model_name: str) -> int:
    """统一通过网关估算文本 token。"""

    return llm_gateway.estimate_text_tokens(text, model_name)


@dataclass(slots=True)
class SessionEvidenceItem:
    """跨轮保存的关键证据。"""

    source: str
    summary: str
    data: Any
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class SessionState:
    """assistant 会话状态。

    先保持轻量：
    - `recent_messages` 保留近几轮原始对话
    - `memory_summary` 负责吸收更早历史
    - `evidence_items` 保存附件事实和工具证据
    """

    session_id: str
    assistant_id: str
    owner_type: str
    owner_key: str
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    memory_summary: str = ""
    evidence_items: list[SessionEvidenceItem] = field(default_factory=list)
    turn_count: int = 0
    last_updated_at: float = field(default_factory=time.time)


class AssistantRequestCancelled(Exception):
    """用户主动取消的 assistant 请求。"""


class AssistantRuntime:
    """通用多轮 assistant 运行时。"""

    def __init__(self, definition_manager, llm_gateway, trace_store: AssistantTraceStore | None = None):
        self.definition_manager = definition_manager
        self.llm = llm_gateway
        self.trace_store = trace_store or AssistantTraceStore(limit=TRACE_RECORD_LIMIT)
        self.attachment_resolver = AttachmentResolver(definition_manager, llm_gateway)
        self._session_states: dict[str, SessionState] = {}
        self._session_lock = threading.Lock()
        self._cancelled_sessions: set[str] = set()
        self._cancel_lock = threading.Lock()

    def cancel_session(self, session_id: str) -> bool:
        """标记指定会话为已取消，等待运行循环在安全点退出。"""
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id: return False
        with self._cancel_lock:
            self._cancelled_sessions.add(normalized_session_id)
        logger.info(f"[AI会话] 收到取消请求 session_id={normalized_session_id}")
        return True

    def clear_cancelled_session(self, session_id: str) -> None:
        """清理会话取消标记，避免后续新请求误命中旧状态。"""
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id: return
        with self._cancel_lock:
            self._cancelled_sessions.discard(normalized_session_id)

    def get_trace_records(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """返回会话级 trace 视图，并补齐前端所需的派生字段。"""
        sessions = self.trace_store.get_trace_records(session_id)
        return [self._enrich_trace_session(session) for session in sessions]

    def _get_or_create_session_state(
        self,
        *,
        session_id: str,
        assistant: AssistantDefinition,
        assistant_context: dict[str, Any],
        payload: dict[str, Any],
    ) -> SessionState:
        """读取或创建会话状态。

        当前仍兼容前端回放 `history`，但只在会话首次出现时用于初始化；
        后续轮次以 runtime 自己维护的状态为准，避免前端历史和工具证据长期漂移。
        """

        with self._session_lock:
            session_state = self._session_states.get(session_id)
            if session_state is None:
                session_state = SessionState(
                    session_id=session_id,
                    assistant_id=assistant.id,
                    owner_type=str(assistant_context.get("owner_type") or "assistant"),
                    owner_key=str(assistant_context.get("owner_key") or ""),
                )
                self._bootstrap_session_history(session_state, payload.get("history", []))
                self._session_states[session_id] = session_state
            session_state.last_updated_at = time.time()
            return session_state

    def _bootstrap_session_history(self, session_state: SessionState, history: list[dict[str, Any]] | None) -> None:
        if session_state.recent_messages: return
        for message in history or []:
            role = str(message.get("role") or "").strip()
            if role not in ("user", "assistant"):
                continue
            content = self._message_text(message.get("content", ""))
            if not content.strip():
                continue
            session_state.recent_messages.append({"role": role, "content": content.strip()})
        self._compact_session_memory(session_state)

    def _build_runtime_trace_payload(self, session_state: SessionState | None) -> dict[str, Any]:
        if session_state is None: return {}
        return {
            "session_id": session_state.session_id,
            "assistant_id": session_state.assistant_id,
            "owner_type": session_state.owner_type,
            "owner_key": session_state.owner_key,
            "turn_count": int(session_state.turn_count or 0),
            "memory_summary": str(session_state.memory_summary or ""),
            "evidence_count": len(session_state.evidence_items),
            "recent_message_count": len(session_state.recent_messages),
        }

    def _build_message_usage_from_request(self, token_usage: dict[str, Any] | None) -> dict[str, Any]:
        token_usage = dict(token_usage or {})
        prompt_tokens = int(token_usage.get("estimated_prompt_tokens", 0) or 0)
        completion_tokens = int(token_usage.get("estimated_completion_tokens", 0) or 0)
        return {
            "user": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
            },
            "assistant": {
                "prompt_tokens": 0,
                "completion_tokens": completion_tokens,
                "total_tokens": completion_tokens,
            },
        }

    def _build_session_usage_summary(self, trace_session: dict[str, Any] | ConversationTraceSession | None) -> dict[str, Any]:
        if trace_session is None: return {}

        if isinstance(trace_session, ConversationTraceSession):
            trace_session = trace_session.model_dump()
        normalized_session = dict(trace_session or {})
        total_token_usage = dict(normalized_session.get("total_token_usage") or {})
        total_message_usage = dict(normalized_session.get("total_message_usage") or {})
        user_usage = dict(total_message_usage.get("user") or {})
        assistant_usage = dict(total_message_usage.get("assistant") or {})
        total_prompt_input_breakdown = dict(normalized_session.get("total_prompt_input_breakdown") or {})
        return {
            "request_count": int(normalized_session.get("request_count") or 0),
            "request_usage": {
                "prompt_tokens": int(total_token_usage.get("prompt_tokens") or 0),
                "completion_tokens": int(total_token_usage.get("completion_tokens") or 0),
                "total_tokens": int(total_token_usage.get("total_tokens") or 0),
                "tool_rounds": int(total_token_usage.get("tool_rounds") or 0),
                "answer_completion_tokens": int(total_token_usage.get("answer_completion_tokens") or 0),
                "reasoning_completion_tokens": int(total_token_usage.get("reasoning_completion_tokens") or 0),
                "tool_call_completion_tokens": int(total_token_usage.get("tool_call_completion_tokens") or 0),
            },
            "message_usage": {
                "user": {
                    "prompt_tokens": int(user_usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(user_usage.get("completion_tokens") or 0),
                    "total_tokens": int(user_usage.get("total_tokens") or 0),
                },
                "assistant": {
                    "prompt_tokens": int(assistant_usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(assistant_usage.get("completion_tokens") or 0),
                    "total_tokens": int(assistant_usage.get("total_tokens") or 0),
                },
            },
            "prompt_input_breakdown": {
                "total_tokens": int(total_prompt_input_breakdown.get("total_tokens") or 0),
                "prompt_template_tokens": int(total_prompt_input_breakdown.get("prompt_template_tokens") or 0),
                "memory_tokens": int(total_prompt_input_breakdown.get("memory_tokens") or 0),
                "attachment_tokens": int(total_prompt_input_breakdown.get("attachment_tokens") or 0),
                "user_input_tokens": int(total_prompt_input_breakdown.get("user_input_tokens") or 0),
                "tool_context_tokens": int(total_prompt_input_breakdown.get("tool_context_tokens") or 0),
                "forced_summary_tokens": int(total_prompt_input_breakdown.get("forced_summary_tokens") or 0),
            },
            "visible_total_tokens": int(user_usage.get("total_tokens") or 0) + int(assistant_usage.get("total_tokens") or 0),
        }

    def _fit_prompt_input_breakdown_total(
        self,
        breakdown: dict[str, Any] | None,
        total_tokens: int,
    ) -> dict[str, int]:
        normalized = create_prompt_input_breakdown()
        for key in normalized:
            if key == "total_tokens":
                continue
            normalized[key] = max(0, int((breakdown or {}).get(key, 0) or 0))
        assigned_total = sum(value for key, value in normalized.items() if key != "total_tokens")
        delta = int(total_tokens or 0) - assigned_total
        if delta > 0:
            normalized["prompt_template_tokens"] += delta
        elif delta < 0:
            overflow = -delta
            for key in ("prompt_template_tokens", "attachment_tokens", "user_input_tokens", "memory_tokens", "tool_context_tokens", "forced_summary_tokens"):
                if overflow <= 0:
                    break
                removable = min(normalized[key], overflow)
                normalized[key] -= removable
                overflow -= removable
        normalized["total_tokens"] = sum(value for key, value in normalized.items() if key != "total_tokens")
        return normalized

    def _merge_prompt_input_breakdown(
        self,
        base_breakdown: dict[str, Any] | None,
        overlay_breakdown: dict[str, Any] | None,
    ) -> dict[str, int]:
        merged = create_prompt_input_breakdown()
        for key in merged:
            merged[key] = int((base_breakdown or {}).get(key, 0) or 0) + int((overlay_breakdown or {}).get(key, 0) or 0)
        return merged

    def _build_base_prompt_input_breakdown(
        self,
        *,
        system_prompt: str,
        memory_messages: list[dict[str, str]],
        user_prompt: str,
        attachment_prompt_block: str,
        question: str,
        base_prompt_tokens: int,
        model_name: str,
    ) -> dict[str, int]:
        system_tokens = self._estimate_messages_tokens([{"role": "system", "content": system_prompt}], model_name) if system_prompt else 0
        memory_tokens = self._estimate_messages_tokens(memory_messages, model_name) if memory_messages else 0
        user_message_tokens = self._estimate_messages_tokens([{"role": "user", "content": user_prompt}], model_name) if user_prompt else 0
        attachment_tokens = self._estimate_text_tokens(attachment_prompt_block, model_name) if attachment_prompt_block else 0
        attachment_tokens = min(max(0, user_message_tokens), max(0, attachment_tokens))
        remaining_user_tokens = max(0, user_message_tokens - attachment_tokens)
        user_input_tokens = self._estimate_text_tokens(question, model_name) if question else 0
        user_input_tokens = min(remaining_user_tokens, max(0, user_input_tokens))
        prompt_template_tokens = max(0, system_tokens + max(0, user_message_tokens - attachment_tokens - user_input_tokens))
        return self._fit_prompt_input_breakdown_total(
            {
                "prompt_template_tokens": prompt_template_tokens,
                "memory_tokens": memory_tokens,
                "attachment_tokens": attachment_tokens,
                "user_input_tokens": user_input_tokens,
            },
            int(base_prompt_tokens or 0),
        )

    def _build_prompt_input_breakdown_for_round(
        self,
        *,
        prompt_tokens_this_round: int,
        base_prompt_tokens: int,
        base_prompt_breakdown: dict[str, Any] | None,
        model_name: str,
        forced_summary_text: str = "",
    ) -> dict[str, int]:
        breakdown = dict(base_prompt_breakdown or create_prompt_input_breakdown())
        forced_summary_tokens = (
            self._estimate_messages_tokens([{"role": "system", "content": forced_summary_text}], model_name)
            if forced_summary_text else 0
        )
        breakdown["forced_summary_tokens"] = int(forced_summary_tokens or 0)
        breakdown["tool_context_tokens"] = max(
            0,
            int(prompt_tokens_this_round or 0) - int(base_prompt_tokens or 0) - int(forced_summary_tokens or 0),
        )
        return self._fit_prompt_input_breakdown_total(breakdown, int(prompt_tokens_this_round or 0))

    def _merge_message_usage(self, base_usage: dict[str, Any] | None, overlay_usage: dict[str, Any] | None) -> dict[str, Any]:
        base_usage = dict(base_usage or {})
        overlay_usage = dict(overlay_usage or {})
        merged = {
            "user": dict(base_usage.get("user") or {}),
            "assistant": dict(base_usage.get("assistant") or {}),
        }
        if overlay_usage.get("user"):
            merged["user"].update(dict(overlay_usage.get("user") or {}))
        if overlay_usage.get("assistant"):
            merged["assistant"].update(dict(overlay_usage.get("assistant") or {}))
        for role in ("user", "assistant"):
            role_usage = merged.get(role) or {}
            prompt_tokens = int(role_usage.get("prompt_tokens") or 0)
            completion_tokens = int(role_usage.get("completion_tokens") or 0)
            role_usage["total_tokens"] = prompt_tokens + completion_tokens
            merged[role] = role_usage
        return merged

    def _emit_request_usage_event(
        self,
        *,
        session_id: str,
        request_id: str,
        token_usage: dict[str, Any],
        message_usage: dict[str, Any],
        prompt_input_breakdown: dict[str, Any] | None = None,
    ) -> None:
        EventBus.emit("ai-request-usage", {
            "session_id": str(session_id or "").strip(),
            "request_id": str(request_id or "").strip(),
            "token_usage": dict(token_usage or {}),
            "message_usage": dict(message_usage or {}),
            "prompt_input_breakdown": dict(prompt_input_breakdown or {}),
        })

    def _enrich_trace_session(self, session_snapshot: dict[str, Any]) -> dict[str, Any]:
        normalized_snapshot = dict(session_snapshot or {})
        session_id = str(normalized_snapshot.get("session_id") or "").strip()
        session_state = self._session_states.get(session_id)
        normalized_snapshot["runtime"] = self._build_runtime_trace_payload(session_state)
        normalized_snapshot["timeline_items"] = self._build_trace_timeline_items(normalized_snapshot)
        return normalized_snapshot

    def _extract_trace_temperature(self, trace: dict[str, Any]) -> str:
        request_payload = trace.get("request_payload",{}) if isinstance(trace.get("request_payload",{}), dict) else {}
        override_config = request_payload.get("ai_override_config",{}) if isinstance(request_payload.get("ai_override_config",{}), dict) else {}
        raw_temperature = override_config.get("temperature", request_payload.get("temperature",""))
        try:
            numeric = float(raw_temperature)
        except (TypeError, ValueError):
            return ""
        return f"{numeric:.1f}"

    def _build_trace_timeline_items(self, session_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        traces = list(session_snapshot.get("traces") or [])
        items: list[dict[str, Any]] = []
        for trace_index, trace in enumerate(traces):
            trace_id = str(trace.get("trace_id") or "").strip()
            trace_started_at = self._normalize_trace_timestamp(trace.get("started_at"))
            trace_finished_at = self._normalize_trace_timestamp(trace.get("finished_at"), trace_started_at)
            trace_temperature = self._extract_trace_temperature(trace)
            items.append({
                "id": f"trace-request-{trace_id or trace_index}",
                "timestamp": trace_started_at,
                "kind": "request",
                "tone": "cool",
                "title": "后端请求进入",
                "badge": str(trace.get("status") or "running"),
                "trace_id": trace_id,
                "body": str(trace.get("user_input_text") or "（空请求）"),
                "attachments": self._build_trace_attachment_labels(trace.get("resolved_attachments")),
                "metrics": [
                    {"label": "模型", "value": str(trace.get("model") or "未知")},
                    {"label": "随机性", "value": trace_temperature or "默认"},
                    {"label": "Prompt", "value": str(trace.get("prompt_id") or "未知")},
                    {"label": "本轮输入", "value": int(((trace.get("message_usage") or {}).get("user") or {}).get("total_tokens") or 0)},
                ],
                "details": {
                    "request_payload": trace.get("request_payload"),
                    "messages_snapshot": trace.get("messages_snapshot"),
                    "resolved_attachments": trace.get("resolved_attachments"),
                    "message_usage": trace.get("message_usage"),
                },
            })

            tool_calls = list(trace.get("tool_calls") or [])
            tool_gap = self._calculate_tool_gap(trace_started_at, trace_finished_at, len(tool_calls))
            for tool_index, tool in enumerate(tool_calls):
                tool_id = str(tool.get("tool_id") or tool_index).strip()
                items.append({
                    "id": f"trace-tool-{trace_id or trace_index}-{tool_id}",
                    "timestamp": trace_started_at + tool_gap * (tool_index + 1),
                    "kind": "tool",
                    "tone": "tip" if str(tool.get("status") or "done") != "error" else "danger",
                    "title": f"工具调用 · {str(tool.get('display_name') or tool.get('name') or 'unknown')}",
                    "badge": str(tool.get("status") or "done"),
                    "trace_id": trace_id,
                    "body": str(tool.get("summary") or ""),
                    "metrics": [
                        {"label": "耗时", "value": f"{int(tool.get('duration_ms') or 0)}ms"},
                        {"label": "工具ID", "value": tool_id or "无"},
                    ],
                    "details": {
                        "name": tool.get("name"),
                        "display_name": tool.get("display_name"),
                        "arguments_preview": tool.get("arguments_preview"),
                        "arguments": tool.get("arguments"),
                        "arguments_pretty": tool.get("arguments_pretty"),
                        "result": tool.get("result"),
                        "result_pretty": tool.get("result_pretty"),
                    },
                })

            items.append({
                "id": f"trace-response-{trace_id or trace_index}",
                "timestamp": trace_finished_at or (trace_started_at + trace_index + TRACE_TOOL_TIME_SPAN_FALLBACK),
                "kind": "response",
                "tone": self._trace_status_tone(str(trace.get("status") or "done")),
                "title": "后端最终输出",
                "badge": str(trace.get("status") or "done"),
                "trace_id": trace_id,
                "body": str(trace.get("final_output") or trace.get("error") or "（空）"),
                "reasoning": str(trace.get("final_reasoning") or ""),
                "metrics": [
                    {"label": "输入Token", "value": int(((trace.get("token_usage") or {}).get("prompt_tokens") or 0))},
                    {"label": "输出Token", "value": int(((trace.get("token_usage") or {}).get("completion_tokens") or 0))},
                    {"label": "正文输出", "value": int(((trace.get("token_usage") or {}).get("answer_completion_tokens") or 0))},
                    {"label": "思考输出", "value": int(((trace.get("token_usage") or {}).get("reasoning_completion_tokens") or 0))},
                    {"label": "工具调用输出", "value": int(((trace.get("token_usage") or {}).get("tool_call_completion_tokens") or 0))},
                    {"label": "总Token", "value": int(((trace.get("token_usage") or {}).get("total_tokens") or 0))},
                    {"label": "工具轮次", "value": int(((trace.get("token_usage") or {}).get("tool_rounds") or 0))},
                    {"label": "本轮输出", "value": int(((trace.get("message_usage") or {}).get("assistant") or {}).get("total_tokens") or 0)},
                ],
                "details": {
                    "response_payload": trace.get("response_payload"),
                    "message_usage": trace.get("message_usage"),
                    "error": trace.get("error"),
                },
            })

        items.sort(
            key=lambda item: (
                self._normalize_trace_timestamp(item.get("timestamp")),
                str(item.get("id") or ""),
            )
        )
        return items

    def _build_trace_attachment_labels(self, attachments: Any) -> list[str]:
        labels: list[str] = []
        for attachment in attachments or []:
            if isinstance(attachment, dict):
                summary = str(
                    attachment.get("summary")
                    or attachment.get("title")
                    or attachment.get("type")
                    or "附件"
                ).strip()
            else:
                summary = str(
                    getattr(attachment, "summary", "")
                    or getattr(attachment, "title", "")
                    or getattr(attachment, "type", "")
                    or "附件"
                ).strip()
            if summary:
                labels.append(summary)
        return labels

    def _calculate_tool_gap(self, started_at: float, finished_at: float, tool_count: int) -> int:
        if tool_count <= 0: return TRACE_TOOL_TIME_SPAN_FALLBACK
        total_span = max(finished_at, started_at + TRACE_TOOL_TIME_SPAN_FALLBACK) - started_at
        return max(TRACE_TOOL_TIME_SPAN_FALLBACK, int(total_span / (tool_count + 1)))

    def _normalize_trace_timestamp(self, value: Any, fallback: float = 0) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return float(fallback or 0)
        return numeric if numeric > 0 else float(fallback or 0)

    def _trace_status_tone(self, status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized == "error": return "danger"
        if normalized == "cancelled": return "warn"
        if normalized == "done": return "success"
        return "special"

    def _build_memory_messages(self, session_state: SessionState) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        memory_summary_block = str(session_state.memory_summary or "").strip()
        memory_evidence_block = self._build_evidence_prompt_block(session_state.evidence_items)
        if memory_summary_block or memory_evidence_block:
            memory_text = self._safe_format(
                ASSISTANT_MEMORY_SYSTEM_TEMPLATE,
                {
                    "memory_summary_block": memory_summary_block or "暂无历史摘要。",
                    "memory_evidence_block": memory_evidence_block or "暂无沉淀证据。",
                },
            ).strip()
            if memory_text:
                messages.append({"role": "system", "content": memory_text})
        messages.extend(
            {
                "role": str(item.get("role") or "").strip(),
                "content": str(item.get("content") or "").strip(),
            }
            for item in (session_state.recent_messages or [])
            if str(item.get("role") or "").strip() in ("user", "assistant")
            and str(item.get("content") or "").strip()
        )
        return messages

    def _build_evidence_prompt_block(self, evidence_items: list[SessionEvidenceItem]) -> str:
        if not evidence_items: return ""
        lines = ["已沉淀证据："]
        for item in evidence_items[-SESSION_EVIDENCE_LIMIT:]:
            line = f"- [{item.source}] {item.summary}"
            data_text = self._message_text(item.data)
            if data_text and data_text != "{}":
                line += f" | 数据: {data_text[:300]}"
            lines.append(line)
        return "\n".join(lines)

    def _commit_session_turn(
        self,
        *,
        session_state: SessionState,
        user_text: str,
        assistant_text: str,
        resolved_attachments: list[ResolvedContextAttachment],
    ) -> None:
        if str(user_text or "").strip():
            session_state.recent_messages.append({"role": "user", "content": str(user_text).strip()})
        if str(assistant_text or "").strip():
            session_state.recent_messages.append({"role": "assistant", "content": str(assistant_text).strip()})
        for attachment in resolved_attachments or []:
            summary = str(attachment.summary or attachment.title or attachment.type or "").strip()
            facts = dict(attachment.facts or {}) if isinstance(attachment.facts, dict) else {}
            if summary or facts:
                self._append_evidence_item(
                    session_state,
                    source=f"attachment:{attachment.type}",
                    summary=summary or "已补齐上下文附件",
                    data=facts,
                )
        session_state.turn_count += 1
        session_state.last_updated_at = time.time()
        self._compact_session_memory(session_state)

    def _append_evidence_item(self, session_state: SessionState, *, source: str, summary: str, data: Any) -> None:
        normalized_summary = str(summary or "").strip()
        if not normalized_summary and not data: return
        signature = json.dumps(
            {"source": source, "summary": normalized_summary, "data": data},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        for existing in session_state.evidence_items[-SESSION_EVIDENCE_LIMIT:]:
            existing_signature = json.dumps(
                {"source": existing.source, "summary": existing.summary, "data": existing.data},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            if existing_signature == signature: return
        session_state.evidence_items.append(
            SessionEvidenceItem(source=source, summary=normalized_summary or "已记录结构化证据", data=data)
        )
        if len(session_state.evidence_items) > SESSION_EVIDENCE_LIMIT:
            session_state.evidence_items = session_state.evidence_items[-SESSION_EVIDENCE_LIMIT:]

    def _compact_session_memory(self, session_state: SessionState) -> None:
        if len(session_state.recent_messages) <= SESSION_RECENT_MESSAGE_LIMIT: return
        overflow = session_state.recent_messages[:-SESSION_RECENT_MESSAGE_LIMIT]
        session_state.recent_messages = session_state.recent_messages[-SESSION_RECENT_MESSAGE_LIMIT:]
        summary_lines = [str(session_state.memory_summary or "").strip()] if session_state.memory_summary else []
        for message in overflow:
            role = "用户" if str(message.get("role") or "") == "user" else "助手"
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            if len(content) > 160:
                content = content[:160].rstrip() + "..."
            summary_lines.append(f"{role}: {content}")
        compact_lines = [line for line in summary_lines if line]
        session_state.memory_summary = "\n".join(compact_lines[-12:]).strip()

    def run_session(self, payload: dict, active_context=None, reader=None) -> dict[str, Any]:
        """执行一次 assistant 会话请求。

        入口负责把外部 payload 规整成稳定会话上下文，再把真正的推理/工具循环
        交给 `_run_session_loop`，这样异常收尾、trace 与取消控制都能统一处理。
        """
        payload = dict(payload or {})
        session_id = str(payload.get("session_id") or uuid.uuid4()).strip()
        trace_record: RequestTraceRecord | None = None
        session_request: dict[str, Any] | None = None
        session_state: SessionState | None = None

        try:
            assistant_context = self._normalize_assistant_context(payload)
            payload = self._build_effective_payload(payload, assistant_context)
            assistant_id = str(assistant_context.get("assistant_id") or "").strip()
            assistant = self._get_assistant_definition(assistant_id)
            assistant_context = self._apply_default_question(
                assistant=assistant,
                payload=payload,
                assistant_context=assistant_context,
            )
            payload = self._build_effective_payload(payload, assistant_context)
            session_state = self._get_or_create_session_state(
                session_id=session_id,
                assistant=assistant,
                assistant_context=assistant_context,
                payload=payload,
            )
            session_request = self._build_session_request(
                session_id=session_id,
                payload=payload,
                assistant=assistant,
                assistant_context=assistant_context,
                session_state=session_state,
                active_context=active_context,
                reader=reader,
            )
            trace_record = session_request["trace_record"]
            self._emit_request_usage_event(
                session_id=session_id,
                request_id=str((assistant_context.get("request_payload") or {}).get("client_request_id") or ""),
                token_usage=session_request.get("initial_request_token_usage") or {},
                message_usage=session_request.get("message_usage") or {},
                prompt_input_breakdown=session_request.get("initial_prompt_input_breakdown") or {},
            )
            self._log_session_start(session_id, assistant, payload.get("history", []), session_request["resolved_attachments"])

            result = self._run_session_loop(
                session_id=session_id,
                messages=session_request["messages"],
                llm_kwargs=session_request["llm_kwargs"],
                model_name=session_request["model_name"],
                token_usage=session_request["token_usage"],
                prompt_input_breakdown=session_request.get("initial_prompt_input_breakdown") or create_prompt_input_breakdown(),
                assistant=assistant,
                tools=session_request["tools"],
                tool_choice=session_request["tool_choice"],
                tool_executor=session_request["tool_executor"],
                trace_record=trace_record,
                session_state=session_state,
                resolved_attachments=session_request["resolved_attachments"],
            )

            if isinstance(result, dict):
                response_payload = dict(result)
                trace_debug_payload = response_payload.pop("_trace_debug", {}) if isinstance(response_payload.get("_trace_debug"), dict) else {}
                result.pop("_trace_debug", None)
                response_payload["message_usage"] = self._merge_message_usage(
                    {},
                    response_payload.get("message_usage") or self._build_message_usage_from_request(response_payload.get("token_usage") or {}),
                )
                self._commit_session_turn(
                    session_state=session_state,
                    user_text=session_request["question"],
                    assistant_text=str(response_payload.get("analysis", "") or ""),
                    resolved_attachments=session_request["resolved_attachments"],
                )
                self.trace_store.finalize_record(
                    trace_record,
                    status="done",
                    final_output=str(response_payload.get("analysis", "") or ""),
                    final_reasoning=str(response_payload.get("reasoning_content", "") or ""),
                    token_usage=response_payload.get("token_usage") or session_request["token_usage"],
                    message_usage=response_payload.get("message_usage") or session_request.get("message_usage") or {},
                    prompt_input_breakdown=response_payload.get("prompt_input_breakdown") or session_request.get("initial_prompt_input_breakdown") or {},
                    response_payload={
                        **response_payload,
                        **trace_debug_payload,
                        "runtime": self._build_runtime_trace_payload(session_state),
                    },
                )
                trace_sessions = self.trace_store.get_trace_records(session_id)
                if trace_sessions:
                    response_payload["session_usage_summary"] = self._build_session_usage_summary(trace_sessions[0])
                result.update({
                    "message_usage": response_payload.get("message_usage") or {},
                    "session_usage_summary": response_payload.get("session_usage_summary") or {},
                })
            return result
        except AssistantRequestCancelled:
            logger.info(f"[AI会话] 用户已取消 session_id={session_id}")
            EventBus.emit("ai-chat-cancelled", {"session_id": session_id})
            token_usage = session_request["token_usage"] if session_request else self._create_token_usage()
            self.trace_store.finalize_record(
                trace_record,
                status="cancelled",
                token_usage=token_usage,
                message_usage=self._build_message_usage_from_request(token_usage),
                prompt_input_breakdown=session_request.get("initial_prompt_input_breakdown") if session_request else create_prompt_input_breakdown(),
                error="cancelled",
                response_payload={
                    "cancelled": True,
                    "message_usage": self._build_message_usage_from_request(token_usage),
                    "prompt_input_breakdown": session_request.get("initial_prompt_input_breakdown") if session_request else create_prompt_input_breakdown(),
                    "runtime": self._build_runtime_trace_payload(session_state),
                },
            )
            trace_sessions = self.trace_store.get_trace_records(session_id)
            return {
                "cancelled": True,
                "analysis": "",
                "actions": [],
                "token_usage": token_usage,
                "message_usage": self._build_message_usage_from_request(token_usage),
                "session_usage_summary": self._build_session_usage_summary(trace_sessions[0]) if trace_sessions else {},
            }
        except Exception as exc:
            token_usage = session_request["token_usage"] if session_request else self._create_token_usage()
            self.trace_store.finalize_record(
                trace_record,
                status="error",
                token_usage=token_usage,
                message_usage=self._build_message_usage_from_request(token_usage),
                prompt_input_breakdown=session_request.get("initial_prompt_input_breakdown") if session_request else create_prompt_input_breakdown(),
                error=str(exc),
                response_payload={
                    "error": str(exc),
                    "message_usage": self._build_message_usage_from_request(token_usage),
                    "prompt_input_breakdown": session_request.get("initial_prompt_input_breakdown") if session_request else create_prompt_input_breakdown(),
                    "runtime": self._build_runtime_trace_payload(session_state),
                },
            )
            trace_sessions = self.trace_store.get_trace_records(session_id)
            if session_request is not None:
                session_request["error_session_usage_summary"] = self._build_session_usage_summary(trace_sessions[0]) if trace_sessions else {}
            raise
        finally:
            self.clear_cancelled_session(session_id)

    def estimate_session_request(self, payload: dict, active_context=None, reader=None) -> dict[str, Any]:
        """估算助手请求输入消耗。

        该入口与正式会话共用同一套 prompt、附件解析和 message 构建逻辑，
        只跳过 trace 创建与模型调用，避免前后端出现两套不同的 token 口径。
        """
        payload = dict(payload or {})
        session_id = str(payload.get("session_id") or uuid.uuid4()).strip()
        assistant_context = self._normalize_assistant_context(payload)
        payload = self._build_effective_payload(payload, assistant_context)
        assistant_id = str(assistant_context.get("assistant_id") or "").strip()
        assistant = self._get_assistant_definition(assistant_id)
        assistant_context = self._apply_default_question(
            assistant=assistant,
            payload=payload,
            assistant_context=assistant_context,
        )
        payload = self._build_effective_payload(payload, assistant_context)
        session_state = self._get_or_create_session_state(
            session_id=session_id,
            assistant=assistant,
            assistant_context=assistant_context,
            payload=payload,
        )
        session_request = self._build_session_request(
            session_id=session_id,
            payload=payload,
            assistant=assistant,
            assistant_context=assistant_context,
            session_state=session_state,
            active_context=active_context,
            reader=reader,
            create_trace_record=False,
        )
        return {
            "session_id": session_id,
            "assistant_id": assistant.id,
            "question": session_request.get("question") or "",
            "message_usage": session_request.get("message_usage") or {},
            "token_usage": session_request.get("initial_request_token_usage") or {},
            "prompt_input_breakdown": session_request.get("initial_prompt_input_breakdown") or {},
        }

    def _normalize_assistant_context(self, payload: dict) -> dict[str, Any]:
        assistant_context = dict(payload.get("assistant_context") or {})
        if assistant_context: return self._merge_assistant_context(payload, assistant_context)

        assistant_id = str(payload.get("assistant_id") or "").strip()
        if not assistant_id:
            raise ValueError("assistant_id is required for assistant session requests")

        assistant_context = {
            "assistant_id": assistant_id,
            "question": str(payload.get("question") or "").strip(),
            "owner_type": str(payload.get("owner_type") or "assistant").strip() or "assistant",
            "owner_key": str(payload.get("owner_key") or "").strip(),
            "override_config": dict(payload.get("ai_override_config") or {}),
            "variables": dict(payload.get("assistant_variables") or {}),
            "request_payload": dict(payload.get("request_payload") or {}),
        }
        return self._merge_assistant_context(payload, assistant_context)

    def _merge_assistant_context(self, payload: dict, assistant_context: dict[str, Any]) -> dict[str, Any]:
        question = str(
            assistant_context.get("question")
            or payload.get("question")
            or assistant_context.get("request_payload", {}).get("question")
            or ""
        ).strip()
        request_payload = dict(assistant_context.get("request_payload") or {})
        request_payload.setdefault("question", question)
        request_payload.setdefault("history", list(payload.get("history", []) or []))
        request_payload.setdefault("attachments", list(payload.get("attachments", []) or []))
        request_payload.setdefault("enabled_tools", list(payload.get("enabled_tools", []) or []))
        request_payload.setdefault("ai_override_config", dict(payload.get("ai_override_config") or assistant_context.get("override_config") or {}))

        assistant_context = {
            **assistant_context,
            "assistant_id": str(assistant_context.get("assistant_id") or payload.get("assistant_id") or "").strip(),
            "question": question,
            "owner_type": str(assistant_context.get("owner_type") or payload.get("owner_type") or "assistant").strip() or "assistant",
            "owner_key": str(assistant_context.get("owner_key") or payload.get("owner_key") or "").strip(),
            "override_config": dict(assistant_context.get("override_config") or payload.get("ai_override_config") or {}),
            "variables": dict(assistant_context.get("variables") or payload.get("assistant_variables") or {}),
            "request_payload": request_payload,
        }
        return assistant_context

    def _build_effective_payload(self, payload: dict[str, Any], assistant_context: dict[str, Any]) -> dict[str, Any]:
        """把 assistant_context.request_payload 提升为运行时统一载荷。

        前端现在只需要发送 canonical 的 `assistant_context`，
        运行时这里负责把问题、附件、工具、覆盖配置等整理成一份稳定结构，
        供会话状态、附件解析、工具执行和 trace 统一消费。
        """

        normalized_payload = dict(payload or {})
        request_payload = dict(assistant_context.get("request_payload") or {})

        question = str(
            assistant_context.get("question")
            or request_payload.get("question")
            or normalized_payload.get("question")
            or ""
        ).strip()
        history = list(request_payload.get("history", []) or normalized_payload.get("history", []) or [])
        attachments = list(request_payload.get("attachments", []) or normalized_payload.get("attachments", []) or [])
        enabled_tools = list(request_payload.get("enabled_tools", []) or normalized_payload.get("enabled_tools", []) or [])
        override_config = dict(
            request_payload.get("ai_override_config")
            or assistant_context.get("override_config")
            or normalized_payload.get("ai_override_config")
            or {}
        )

        source_type = str(
            request_payload.get("source_type")
            or request_payload.get("log_source_type")
            or normalized_payload.get("log_source_type")
            or ""
        ).strip()
        filename = str(request_payload.get("filename") or normalized_payload.get("filename") or "").strip()

        normalized_payload.update({
            "question": question,
            "history": history,
            "attachments": attachments,
            "enabled_tools": enabled_tools,
            "ai_override_config": override_config,
        })
        if source_type:
            normalized_payload["log_source_type"] = source_type
        if filename:
            normalized_payload["filename"] = filename
        return normalized_payload

    def _apply_default_question(
        self,
        *,
        assistant: AssistantDefinition,
        payload: dict[str, Any],
        assistant_context: dict[str, Any],
    ) -> dict[str, Any]:
        question = str(
            assistant_context.get("question")
            or payload.get("question")
            or assistant_context.get("request_payload", {}).get("question")
            or ""
        ).strip()
        if question: return assistant_context

        attachments = list(
            payload.get("attachments", [])
            or assistant_context.get("request_payload", {}).get("attachments", [])
            or []
        )
        fallback_question = self._resolve_default_question(assistant.id, attachments)
        if not fallback_question: return assistant_context

        request_payload = dict(assistant_context.get("request_payload") or {})
        request_payload["question"] = fallback_question
        request_payload.setdefault("attachments", attachments)
        payload["question"] = fallback_question
        assistant_context["question"] = fallback_question
        assistant_context["request_payload"] = request_payload
        return assistant_context

    def _resolve_default_question(self, assistant_id: str, attachments: list[dict[str, Any]]) -> str:
        normalized_assistant_id = str(assistant_id or "").strip()
        if normalized_assistant_id not in {"assistant.log_game", "assistant.log_app"}: return ""
        diagnosis_attachment = self._find_attachment_by_kind(attachments, "diagnosis_context")
        if diagnosis_attachment is None: return ""
        selector = diagnosis_attachment.get("selector") if isinstance(diagnosis_attachment, dict) else {}
        selector_mode = str((selector or {}).get("mode") or "").strip().lower()
        if selector_mode == "all": return DEFAULT_LOG_GLOBAL_SCAN_QUESTION
        return DEFAULT_LOG_ASSISTANT_QUESTION

    def _find_attachment_by_kind(self, attachments: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
        normalized_kind = str(kind or "").strip()
        if not normalized_kind: return None
        for attachment in attachments or []:
            if not isinstance(attachment, dict):
                continue
            if str(attachment.get("kind") or "").strip() == normalized_kind:
                return attachment
        return None

    def _get_assistant_definition(self, assistant_id: str) -> AssistantDefinition:
        assistant_data = self.definition_manager.assistants.get(assistant_id)
        if not assistant_data:
            raise ValueError(f"Assistant definition '{assistant_id}' not found.")
        assistant = AssistantDefinition.model_validate(assistant_data)
        prompt_data = self._get_prompt_config(assistant.prompt_id)
        if prompt_data.get("category") != "assistant":
            raise ValueError(
                f"Assistant definition '{assistant_id}' must bind an assistant prompt, got '{assistant.prompt_id}'."
            )
        return assistant

    def _get_prompt_config(self, prompt_id: str) -> dict[str, Any]:
        return get_prompt_config(self.definition_manager.prompts, prompt_id)

    def _create_token_usage(self, model_name: str = "") -> dict[str, Any]:
        return create_token_usage(model_name)

    def _get_llm_kwargs(self, override_config: dict | None = None) -> dict[str, Any]:
        return build_llm_kwargs(self.llm, override_config)

    def _build_session_request(
        self,
        *,
        session_id: str,
        payload: dict,
        assistant: AssistantDefinition,
        assistant_context: dict[str, Any],
        session_state: SessionState,
        active_context=None,
        reader=None,
        create_trace_record: bool = True,
    ) -> dict[str, Any]:
        override_config = dict(assistant_context.get("override_config") or payload.get("ai_override_config") or {})
        tool_executor = AIToolExecutor(active_context, payload, reader)
        resolved_attachments = self.attachment_resolver.resolve_many(
            payload,
            active_context=active_context,
            reader=reader,
            prompt_id=assistant.prompt_id,
        )
        prompt_config = self._get_prompt_config(assistant.prompt_id)
        variables, tools, tool_choice = self._build_session_variables(
            payload=payload,
            assistant=assistant,
            tool_executor=tool_executor,
            resolved_attachments=resolved_attachments,
            assistant_context=assistant_context,
        )
        prompt_config = self._build_prompt_config(prompt_config, variables)
        messages, prompt_trace_context = self._build_prompt_messages(
            prompt_config,
            variables,
            session_state,
        )
        llm_kwargs = self._get_llm_kwargs(override_config)
        model_name = str(llm_kwargs.get("model", settings.config.ai.model) or settings.config.ai.model)
        token_usage = self._create_token_usage(model_name)
        initial_request_token_usage = self._create_token_usage(model_name)
        initial_request_token_usage["estimated_prompt_tokens"] = self._estimate_messages_tokens(messages, model_name)
        initial_request_token_usage["estimated_total_tokens"] = initial_request_token_usage["estimated_prompt_tokens"]
        initial_prompt_input_breakdown = self._build_base_prompt_input_breakdown(
            system_prompt=str(prompt_trace_context.get("system_prompt") or ""),
            memory_messages=list(prompt_trace_context.get("memory_messages") or []),
            user_prompt=str(prompt_trace_context.get("user_prompt") or ""),
            attachment_prompt_block=str(prompt_trace_context.get("attachment_prompt_block") or ""),
            question=str(prompt_trace_context.get("question") or ""),
            base_prompt_tokens=int(initial_request_token_usage["estimated_prompt_tokens"] or 0),
            model_name=model_name,
        )
        initial_message_usage = self._build_message_usage_from_request(initial_request_token_usage)
        question = str(assistant_context.get("question") or "").strip()
        request_payload = dict(assistant_context.get("request_payload") or {})
        trace_record = None
        if create_trace_record:
            trace_record = self.trace_store.create_record(
                session_id=session_id,
                assistant_id=assistant.id,
                owner_type=str(assistant_context.get("owner_type") or "assistant"),
                owner_key=str(assistant_context.get("owner_key") or ""),
                prompt_id=assistant.prompt_id,
                model=str(model_name or ""),
                user_input_text=question,
                messages_snapshot=messages,
                request_payload=request_payload,
                raw_attachments=list(payload.get("attachments", []) or []),
                resolved_attachments=resolved_attachments,
            )
        return {
            "assistant": assistant,
            "assistant_context": assistant_context,
            "resolved_attachments": resolved_attachments,
            "prompt_config": prompt_config,
            "variables": variables,
            "tools": tools,
            "tool_choice": tool_choice,
            "messages": messages,
            "llm_kwargs": llm_kwargs,
            "model_name": model_name,
            "token_usage": token_usage,
            "message_usage": initial_message_usage,
            "initial_request_token_usage": initial_request_token_usage,
            "initial_prompt_input_breakdown": initial_prompt_input_breakdown,
            "prompt_trace_context": prompt_trace_context,
            "trace_record": trace_record,
            "question": question,
            "owner_type": str(assistant_context.get("owner_type") or "assistant"),
            "owner_key": str(assistant_context.get("owner_key") or ""),
            "tool_executor": tool_executor,
            "session_state": session_state,
        }

    def _log_session_start(
        self,
        session_id: str,
        assistant: AssistantDefinition,
        history: list[dict],
        resolved_attachments: list[ResolvedContextAttachment],
    ) -> None:
        attachment_count = len(resolved_attachments or [])
        logger.debug(
            f"[AI会话] 会话开始 session_id={session_id} assistant={assistant.id} "
            f"history={len(history)} attachments={attachment_count}"
        )

    def _build_session_variables(
        self,
        *,
        payload: dict,
        assistant: AssistantDefinition,
        tool_executor: AIToolExecutor,
        resolved_attachments: list[ResolvedContextAttachment] | None = None,
        assistant_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], Any, Any]:
        variables = {
            "target_lang": get_lang_by_code(settings.config.language),
            "current_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tools_description": "",
            "output_contract": self._build_assistant_output_contract(assistant),
            "attachments_block": self.attachment_resolver.build_prompt_block(resolved_attachments or []),
            "message": str(
                (assistant_context or {}).get("question")
                or payload.get("question")
                or (assistant_context or {}).get("request_payload", {}).get("question")
                or ""
            ).strip(),
        }
        variables.update(self.attachment_resolver.extract_prompt_variables(resolved_attachments or []))
        assistant_variables = {}
        if isinstance(assistant_context, dict):
            assistant_variables.update(dict(assistant_context.get("variables") or {}))
        if assistant_variables:
            variables.update(assistant_variables)

        requested_tools = list(payload.get("enabled_tools", []) or [])
        allowed_tools = list(assistant.tool_scope_selectable or [])
        tools = None
        tool_choice = None
        if allowed_tools:
            if not requested_tools:
                requested_tools = list(allowed_tools)
            requested_tool_names = [name for name in requested_tools if name in allowed_tools]
            if requested_tool_names:
                tools = tool_executor.get_tool_schemas(requested_tool_names)
                tool_choice = "auto"
                variables["tools_description"] = self._build_tools_description(tools)
            else:
                variables["tools_description"] = "本轮不可调用外部工具，只能基于当前上下文作答。"
        return variables, tools, tool_choice

    def _build_tools_description(self, tools: list[dict[str, Any]] | None) -> str:
        if not tools: return "本轮不可调用外部工具，只能基于当前上下文作答。"
        tool_lines = []
        for tool in tools:
            name = str(tool.get("function", {}).get("name") or "").strip()
            if not name:
                continue
            hint = str(tool.get("function", {}).get("description") or "").strip()
            tool_lines.append(f"- {name}: {hint}")
        return "可用工具：\n" + "\n".join(tool_lines) if tool_lines else "本轮不可调用外部工具，只能基于当前上下文作答。"

    def _build_prompt_config(self, base_prompt_config: dict, variables: dict) -> dict:
        prompt_config = dict(base_prompt_config or {})
        system_text = str(prompt_config.get("system") or "")
        tool_suffix = self._safe_format(GENERIC_ASSISTANT_SUFFIX_TEMPLATE, variables)
        prompt_config["system"] = f"{system_text}\n\n{tool_suffix}".strip() if tool_suffix else system_text
        return prompt_config

    def _build_prompt_messages(
        self,
        prompt_config: dict,
        variables: dict,
        session_state: SessionState,
    ) -> tuple[list[dict], dict[str, Any]]:
        system_prompt = self._safe_format(prompt_config.get("system", ""), variables)
        user_prompt = self._safe_format(prompt_config.get("user_template", ""), variables)
        memory_messages = self._build_memory_messages(session_state)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(memory_messages)
        messages.append({"role": "user", "content": user_prompt})
        return messages, {
            "system_prompt": system_prompt,
            "memory_messages": memory_messages,
            "user_prompt": user_prompt,
            "attachment_prompt_block": str(variables.get("attachments_block") or ""),
            "question": str(variables.get("message") or ""),
        }

    def _safe_format(self, template: str, variables: dict[str, Any]) -> str:
        return safe_format_template(template, variables)

    def _message_text(self, content: Any) -> str:
        return normalize_message_text(self.llm, content)

    def _normalize_reasoning_content(self, reasoning_content: Any) -> str:
        return self._message_text(reasoning_content)

    def _extract_reasoning_content(self, obj: Any) -> str:
        """兼容 reasoning_content 与 vLLM 新版 reasoning 字段。"""
        reasoning_content = getattr(obj, "reasoning_content", None)
        if reasoning_content is None or reasoning_content == "":
            reasoning_content = getattr(obj, "reasoning", "")
        return self._normalize_reasoning_content(reasoning_content)

    def _split_inline_reasoning_from_content(self, content: str, existing_reasoning: str = "") -> tuple[str, str]:
        """兼容本地模型把思考过程直接包在 <think>...</think> 中输出。"""
        normalized_content = str(content or "")
        match = re.match(r"^\s*<think>\s*([\s\S]*?)\s*</think>\s*", normalized_content, flags=re.IGNORECASE)
        if not match:
            return normalized_content, str(existing_reasoning or "")

        inline_reasoning = match.group(1).strip()
        remaining_content = normalized_content[match.end():]
        reasoning_parts = [part for part in (str(existing_reasoning or "").strip(), inline_reasoning) if part]
        return remaining_content, "\n".join(reasoning_parts)

    def _estimate_text_tokens(self, text: str, model_name: str) -> int:
        return estimate_text_tokens(self.llm, text, model_name)

    def _estimate_messages_tokens(self, messages: list[dict], model_name: str) -> int:
        return self.llm.estimate_messages_tokens(messages, model_name)

    def _is_retryable_stream_error(self, error: Exception) -> bool:
        error_text = str(error or "").lower()
        retry_signals = (
            "midstreamfallbackerror",
            "incomplete chunked read",
            "peer closed connection",
            "connection aborted",
            "server disconnected",
            "chunkedencodingerror",
        )
        return any(signal in error_text for signal in retry_signals)

    def _parse_dsml_tool_calls(self, text: str) -> list[dict[str, Any]]:
        normalized_text = str(text or "").strip()
        if not normalized_text: return []
        tool_open = "<｜｜DSML｜｜tool_calls>"
        tool_close = "</｜｜DSML｜｜tool_calls>"
        if not normalized_text.startswith(tool_open) or not normalized_text.endswith(tool_close): return []

        inner_text = normalized_text[len(tool_open):-len(tool_close)].strip()
        if not inner_text: return []

        invoke_pattern = re.compile(
            r'<｜｜DSML｜｜invoke\s+name="([^"]+)">\s*([\s\S]*?)\s*</｜｜DSML｜｜invoke>',
            re.IGNORECASE,
        )
        param_pattern = re.compile(
            r'<｜｜DSML｜｜parameter\s+name="([^"]+)"[^>]*>([\s\S]*?)</｜｜DSML｜｜parameter>',
            re.IGNORECASE,
        )

        formatted_tool_calls: list[dict[str, Any]] = []
        for index, invoke_match in enumerate(invoke_pattern.finditer(inner_text)):
            tool_name = str(invoke_match.group(1) or "").strip()
            if not tool_name:
                continue
            invoke_body = str(invoke_match.group(2) or "")
            arguments: dict[str, Any] = {}
            for param_match in param_pattern.finditer(invoke_body):
                param_name = str(param_match.group(1) or "").strip()
                if not param_name:
                    continue
                arguments[param_name] = str(param_match.group(2) or "").strip()
            formatted_tool_calls.append({
                "id": f"dsml_tool_call_{index}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            })
        return formatted_tool_calls

    def _format_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        formatted_tool_calls = []
        for index, tool_call in enumerate(tool_calls):
            function_obj = getattr(tool_call, "function", None)
            formatted_tool_calls.append({
                "id": getattr(tool_call, "id", None) or f"tool_call_{index}",
                "type": getattr(tool_call, "type", None) or "function",
                "function": {
                    "name": getattr(function_obj, "name", None) or "",
                    "arguments": getattr(function_obj, "arguments", None) or "{}",
                },
            })
        return formatted_tool_calls

    def _is_tool_unsupported_error(self, exc: Exception) -> bool:
        """识别模型/接口明确拒绝原生工具调用的错误。"""
        text = str(exc or "").lower()
        signals = (
            "does not support tools",
            "tools are not supported",
            "tool calling is not supported",
            "tool calls are not supported",
            "unsupported tools",
            "unsupported tool",
        )
        return any(signal in text for signal in signals)

    def _messages_with_tool_fallback_notice(self, messages: list[dict]) -> list[dict]:
        """为不支持原生工具调用的降级请求补充约束说明。

        不把 system 提示追加到末尾：部分 Ollama 模型的 chat template 要求末尾
        是真实用户/助手内容，末尾 system 会触发 "no input provided"。
        """
        fallback_messages = []
        notice_inserted = False
        for message in (messages or []):
            next_message = dict(message)
            if not notice_inserted and str(next_message.get("role") or "").lower() == "system":
                content = self._message_text(next_message.get("content", "")).strip()
                next_message["content"] = (
                    f"{TOOL_UNSUPPORTED_FALLBACK_NOTICE}\n\n{content}"
                    if content
                    else TOOL_UNSUPPORTED_FALLBACK_NOTICE
                )
                notice_inserted = True
            fallback_messages.append(next_message)
        if not notice_inserted:
            fallback_messages.insert(0, {"role": "system", "content": TOOL_UNSUPPORTED_FALLBACK_NOTICE})
        return fallback_messages

    def _attach_completion_warning(self, result: dict[str, Any], warning: dict[str, str]) -> dict[str, Any]:
        """给 completion 结果追加用户可见的结构化警告。"""
        next_result = dict(result or {})
        warnings = [dict(item) for item in (next_result.get("warnings") or []) if isinstance(item, dict)]
        warning_code = str(warning.get("code") or "")
        if not any(str(item.get("code") or "") == warning_code for item in warnings):
            warnings.append(dict(warning))
        next_result["warnings"] = warnings
        return next_result

    def _run_completion_with_fallback(
        self,
        *,
        messages: list[dict],
        llm_kwargs: dict,
        session_id: str,
        tools=None,
        tool_choice=None,
    ) -> dict[str, Any]:
        try:
            return self._stream_completion(messages=messages, llm_kwargs=llm_kwargs, session_id=session_id, tools=tools, tool_choice=tool_choice)
        except AssistantRequestCancelled:
            raise
        except Exception as exc:
            if tools is not None and self._is_tool_unsupported_error(exc):
                logger.warning(
                    f"[AI会话] 当前模型不支持原生工具调用，自动禁用工具后重试 session_id={session_id} "
                    f"error={type(exc).__name__}: {exc}"
                )
                fallback_messages = self._messages_with_tool_fallback_notice(messages)
                try:
                    return self._attach_completion_warning(
                        self._stream_completion(
                            messages=fallback_messages,
                            llm_kwargs=llm_kwargs,
                            session_id=session_id,
                            tools=None,
                            tool_choice=None,
                        ),
                        TOOL_UNSUPPORTED_USER_WARNING,
                    )
                except AssistantRequestCancelled:
                    raise
                except Exception as fallback_exc:
                    if not self._is_retryable_stream_error(fallback_exc):
                        raise
                    logger.warning(
                        f"[AI会话] 工具降级后的流式输出中断，自动回退为非流式补救 "
                        f"session_id={session_id} error={type(fallback_exc).__name__}: {fallback_exc}"
                    )
                    return self._attach_completion_warning(
                        self._complete_without_stream(
                            messages=fallback_messages,
                            llm_kwargs=llm_kwargs,
                            tools=None,
                            tool_choice=None,
                        ),
                        TOOL_UNSUPPORTED_USER_WARNING,
                    )
            if not self._is_retryable_stream_error(exc):
                raise
            logger.warning(
                f"[AI会话] 流式输出中断，自动回退为非流式补救 session_id={session_id} error={type(exc).__name__}: {exc}"
            )
            return self._complete_without_stream(messages=messages, llm_kwargs=llm_kwargs, tools=tools, tool_choice=tool_choice)

    def _complete_without_stream(self, messages: list[dict], llm_kwargs: dict, tools=None, tool_choice=None) -> dict[str, Any]:
        request_kwargs = dict(llm_kwargs)
        if tools is not None:
            request_kwargs["tools"] = tools
        if tool_choice is not None:
            request_kwargs["tool_choice"] = tool_choice

        response = self.llm.completion(messages=messages, llm_kwargs=request_kwargs)
        message = response.choices[0].message  # type: ignore
        tool_calls = getattr(message, "tool_calls", None) or []
        content_text, reasoning_content = self._split_inline_reasoning_from_content(
            self._message_text(getattr(message, "content", "")),
            self._extract_reasoning_content(message),
        )

        if tool_calls:
            assistant_message = {
                "is_tool_call": True,
                "tool_calls": self._format_tool_calls(tool_calls),
                "final_text": "",
                "warnings": [],
            }
            if reasoning_content:
                assistant_message["final_think"] = reasoning_content
            return assistant_message

        dsml_tool_calls = self._parse_dsml_tool_calls(content_text)
        if dsml_tool_calls:
            logger.warning(f"[AI会话] 检测到 DSML 伪工具调用文本，已回收为 tool_calls count={len(dsml_tool_calls)}")
            assistant_message = {
                "is_tool_call": True,
                "tool_calls": dsml_tool_calls,
                "final_text": "",
                "warnings": [],
            }
            if reasoning_content:
                assistant_message["final_think"] = reasoning_content
            return assistant_message

        return {
            "is_tool_call": False,
            "tool_calls": [],
            "final_think": reasoning_content,
            "final_text": content_text,
            "warnings": [],
        }

    def _stream_completion(self, messages, llm_kwargs, session_id, tools=None, tool_choice=None):
        response = self.llm.completion(
            messages=messages,
            llm_kwargs=llm_kwargs,
            stream=True,
            tools=tools,
            tool_choice=(tool_choice or "auto") if tools is not None else None,
        )
        self._raise_if_cancelled(session_id, response)
        is_tool_call = False
        tool_calls_dict: dict[int, dict[str, str]] = {}
        final_text = ""
        final_think = ""
        streamed_visible_text = ""

        for chunk in response:  # type: ignore
            self._raise_if_cancelled(session_id, response)
            if isinstance(chunk, tuple) or not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta:
                continue
            if getattr(delta, "tool_calls", None):
                is_tool_call = True
                for tc in (delta.tool_calls or []):
                    idx = tc.index
                    if idx not in tool_calls_dict:
                        tool_calls_dict[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id and not tool_calls_dict[idx]["id"]:
                        tool_calls_dict[idx]["id"] = tc.id
                    if getattr(tc.function, "name", None) and not tool_calls_dict[idx]["name"]:
                        tool_calls_dict[idx]["name"] = tc.function.name or ""
                    if getattr(tc.function, "arguments", None):
                        tool_calls_dict[idx]["arguments"] += tc.function.arguments or ""

            think_chunk = self._extract_reasoning_content(delta)
            if think_chunk:
                final_think += think_chunk
                EventBus.emit("ai-chat-stream", {"session_id": session_id, "type": "reasoning", "chunk": think_chunk})

            if getattr(delta, "content", None):
                content_chunk = self._message_text(delta.content)
                if content_chunk:
                    final_text += content_chunk
                    visible_text = self._extract_streaming_analysis_preview(final_text)
                    if visible_text.startswith(streamed_visible_text) and len(visible_text) > len(streamed_visible_text):
                        next_chunk = visible_text[len(streamed_visible_text):]
                        streamed_visible_text = visible_text
                        EventBus.emit("ai-chat-stream", {"session_id": session_id, "type": "content", "chunk": next_chunk})

        self._raise_if_cancelled(session_id, response)
        formatted_tool_calls = []
        final_text, final_think = self._split_inline_reasoning_from_content(final_text, final_think)

        if is_tool_call:
            for _, tc in sorted(tool_calls_dict.items()):
                formatted_tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })
        elif final_text:
            dsml_tool_calls = self._parse_dsml_tool_calls(final_text)
            if dsml_tool_calls:
                logger.warning(f"[AI会话] 检测到 DSML 伪工具调用文本，已回收为 tool_calls count={len(dsml_tool_calls)}")
                return {
                    "is_tool_call": True,
                    "tool_calls": dsml_tool_calls,
                    "final_think": final_think,
                    "final_text": "",
                    "warnings": [],
                }

        return {
            "is_tool_call": is_tool_call,
            "tool_calls": formatted_tool_calls,
            "final_think": final_think,
            "final_text": final_text,
            "warnings": [],
        }

    def _extract_streaming_analysis_preview(self, text: str) -> str:
        normalized_text = str(text or "")
        if not normalized_text: return ""

        match = re.search(r'"analysis"\s*:\s*"', normalized_text)
        if not match: return ""

        index = match.end()
        decoded_chars: list[str] = []
        text_len = len(normalized_text)
        while index < text_len:
            char = normalized_text[index]
            if char == '"':
                break
            if char != "\\":
                decoded_chars.append(char)
                index += 1
                continue

            index += 1
            if index >= text_len:
                break
            escape_char = normalized_text[index]
            escape_map = {
                '"': '"',
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }
            if escape_char in escape_map:
                decoded_chars.append(escape_map[escape_char])
                index += 1
                continue
            if escape_char == "u":
                unicode_fragment = normalized_text[index + 1:index + 5]
                if len(unicode_fragment) < 4 or not re.fullmatch(r"[0-9a-fA-F]{4}", unicode_fragment):
                    break
                decoded_chars.append(chr(int(unicode_fragment, 16)))
                index += 5
                continue

            decoded_chars.append(escape_char)
            index += 1

        return "".join(decoded_chars)

    def _raise_if_cancelled(self, session_id: str, stream_response=None) -> None:
        if not self._is_cancelled(session_id): return
        try:
            closer = getattr(stream_response, "close", None)
            if callable(closer):
                closer()
        except Exception:
            pass
        raise AssistantRequestCancelled(f"AI assistant session cancelled: {session_id}")

    def _is_cancelled(self, session_id: str) -> bool:
        if not session_id: return False
        with self._cancel_lock: return session_id in self._cancelled_sessions

    def _run_session_loop(
        self,
        *,
        session_id: str,
        messages: list[dict],
        llm_kwargs: dict,
        model_name: str,
        token_usage: dict[str, Any],
        prompt_input_breakdown: dict[str, Any],
        assistant: AssistantDefinition,
        tools,
        tool_choice,
        tool_executor: AIToolExecutor,
        trace_record: RequestTraceRecord | None = None,
        session_state: SessionState,
        resolved_attachments: list[ResolvedContextAttachment],
    ) -> dict[str, Any]:
        loop_count = 0
        executed_tool_signatures: set[str] = set()
        base_prompt_tokens = int((prompt_input_breakdown or {}).get("total_tokens", 0) or 0)
        cumulative_prompt_input_breakdown = create_prompt_input_breakdown()

        while loop_count < ASSISTANT_MAX_LOOPS:
            loop_count += 1
            try:
                prompt_tokens_this_round = self._estimate_messages_tokens(messages, model_name)
                token_usage["estimated_prompt_tokens"] += prompt_tokens_this_round
                token_usage["estimated_total_tokens"] += prompt_tokens_this_round
                round_prompt_input_breakdown = self._build_prompt_input_breakdown_for_round(
                    prompt_tokens_this_round=prompt_tokens_this_round,
                    base_prompt_tokens=base_prompt_tokens,
                    base_prompt_breakdown=prompt_input_breakdown,
                    model_name=model_name,
                )
                cumulative_prompt_input_breakdown = self._merge_prompt_input_breakdown(
                    cumulative_prompt_input_breakdown,
                    round_prompt_input_breakdown,
                )
                logger.debug(
                    f"[AI会话] 进入工具轮 session_id={session_id} loop={loop_count}/{ASSISTANT_MAX_LOOPS} "
                    f"messages={len(messages)} prompt_tokens≈{prompt_tokens_this_round}"
                )
                stream_result = self._run_completion_with_fallback(
                    messages=messages,
                    llm_kwargs=llm_kwargs,
                    session_id=session_id,
                    tools=tools,
                    tool_choice=tool_choice,
                )
                reasoning_text = str(stream_result.get("final_think") or "")
                reasoning_output_tk = self._estimate_text_tokens(reasoning_text, model_name) if reasoning_text else 0
                if stream_result["is_tool_call"]:
                    tool_call_payload = json.dumps(stream_result["tool_calls"], ensure_ascii=False)
                    tool_call_output_tk = self._estimate_text_tokens(tool_call_payload, model_name)
                    answer_output_tk = 0
                else:
                    tool_call_payload = ""
                    tool_call_output_tk = 0
                    answer_output_tk = self._estimate_text_tokens(stream_result["final_text"], model_name)

                output_tk = answer_output_tk + reasoning_output_tk + tool_call_output_tk
                token_usage["estimated_answer_completion_tokens"] += answer_output_tk
                token_usage["estimated_reasoning_completion_tokens"] += reasoning_output_tk
                token_usage["estimated_tool_call_completion_tokens"] += tool_call_output_tk
                token_usage["estimated_completion_tokens"] += output_tk
                token_usage["estimated_total_tokens"] += output_tk

                if stream_result["is_tool_call"]:
                    token_usage["tool_rounds"] += 1
                    assistant_message = {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": stream_result["tool_calls"],
                    }
                    if stream_result.get("final_think"):
                        assistant_message["reasoning_content"] = stream_result["final_think"]
                    messages.append(assistant_message)
                    self._execute_tool_calls(
                        session_id=session_id,
                        formatted_tool_calls=stream_result["tool_calls"],
                        tool_executor=tool_executor,
                        messages=messages,
                        executed_tool_signatures=executed_tool_signatures,
                        trace_record=trace_record,
                        session_state=session_state,
                    )
                    continue

                final_response = self._parse_final_text(
                    stream_result["final_text"],
                    stream_result.get("final_think", ""),
                    assistant=assistant,
                )
                final_response["warnings"] = list(stream_result.get("warnings") or [])
                final_response["reasoning_content"] = reasoning_text
                token_usage["estimated_total_tokens"] = (
                    token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
                )
                final_response["message_usage"] = self._build_message_usage_from_request(token_usage)
                final_response["token_usage"] = token_usage
                final_response["prompt_input_breakdown"] = cumulative_prompt_input_breakdown
                logger.debug(
                    f"[AI会话] 会话完成 session_id={session_id} loop={loop_count} "
                    f"analysis_chars={len(final_response.get('analysis', ''))} "
                    f"total_tokens≈{token_usage['estimated_total_tokens']}"
                )
                return final_response
            except AssistantRequestCancelled:
                raise
            except Exception as exc:
                logger.error(
                    "AI 会话执行失败。session_id=%s",
                    session_id,
                    extra={"error_code": "AI.SESSION.RUN_FAILED", "extra_context": {"session_id": session_id, "original_error": str(exc)}},
                    exc_info=True,
                )
                return self._build_error_response(exc, token_usage)

        return self._build_forced_summary(
            session_id,
            messages,
            llm_kwargs,
            model_name,
            token_usage,
            assistant=assistant,
            prompt_input_breakdown=prompt_input_breakdown,
            accumulated_prompt_input_breakdown=cumulative_prompt_input_breakdown,
        )

    def _execute_tool_calls(
        self,
        *,
        session_id: str,
        formatted_tool_calls: list[dict[str, Any]],
        tool_executor: AIToolExecutor,
        messages: list[dict],
        executed_tool_signatures: set[str],
        trace_record: RequestTraceRecord | None = None,
        session_state: SessionState,
    ) -> None:
        for tc in formatted_tool_calls:
            func_name = tc["function"]["name"]
            func_args = tc["function"]["arguments"]
            tool_start_at = time.perf_counter()
            tool_display = tool_executor.build_tool_call_display(func_name, func_args)

            EventBus.emit("ai-tool-call", {
                "session_id": session_id,
                "tool_id": tc["id"],
                "name": func_name,
                "display_name": tool_display.get("display_name", ""),
                "arguments": func_args,
                "arguments_preview": tool_display.get("arguments_preview", ""),
                "arguments_pretty": tool_display.get("arguments_pretty", ""),
            })

            call_signature = f"{func_name}|{func_args}"
            if call_signature in executed_tool_signatures:
                tool_execution = ToolExecutionResult(
                    name=func_name,
                    ok=False,
                    model_output=json.dumps({"error": DUPLICATE_TOOL_CALL_ERROR}, ensure_ascii=False),
                    data={"error": DUPLICATE_TOOL_CALL_ERROR},
                    summary=f"执行失败：{DUPLICATE_TOOL_CALL_ERROR}",
                    error=DUPLICATE_TOOL_CALL_ERROR,
                )
                logger.warning(f"[AI防死锁] 拦截重复调用: {call_signature}")
            else:
                executed_tool_signatures.add(call_signature)
                self._raise_if_cancelled(session_id)
                try:
                    tool_execution = tool_executor.execute_structured(func_name, func_args)
                except AssistantRequestCancelled:
                    raise
                except Exception as tool_err:
                    logger.error(f"[AI会话] 工具执行异常 tool={func_name}: {tool_err}", exc_info=True)
                    tool_execution = ToolExecutionResult(
                        name=func_name,
                        ok=False,
                        model_output=json.dumps({"error": f"工具 {func_name} 执行异常: {str(tool_err)}"}, ensure_ascii=False),
                        data={"error": f"工具 {func_name} 执行异常: {str(tool_err)}"},
                        summary=f"执行失败：工具 {func_name} 执行异常: {str(tool_err)}",
                        error=str(tool_err),
                    )
                self._raise_if_cancelled(session_id)

            duration_ms = int((time.perf_counter() - tool_start_at) * 1000)
            tool_ok = bool(tool_execution.ok)
            tool_summary = str(tool_execution.summary or "").strip() or self._summarize_tool_result(
                func_name,
                tool_execution.model_output,
            )
            result_display = tool_executor.build_tool_result_display(tool_execution)
            if trace_record is not None:
                trace_record.tool_calls.append(
                    RequestToolCallTrace(
                        tool_id=tc["id"],
                        name=func_name,
                        arguments=func_args,
                        status="done" if tool_ok else "error",
                        result=tool_execution.model_output,
                        duration_ms=duration_ms,
                        summary=tool_summary,
                        display_name=tool_display.get("display_name", ""),
                        arguments_preview=tool_display.get("arguments_preview", ""),
                        arguments_pretty=tool_display.get("arguments_pretty", ""),
                        result_pretty=result_display.get("result_pretty", ""),
                    )
                )

            EventBus.emit("ai-tool-result", {
                "session_id": session_id,
                "tool_id": tc["id"],
                "status": "done" if tool_ok else "error",
                "duration_ms": duration_ms,
                "display_name": result_display.get("display_name", ""),
                "summary": tool_summary,
                "result": tool_execution.model_output,
                "result_pretty": result_display.get("result_pretty", ""),
            })
            self._append_evidence_item(
                session_state,
                source=f"tool:{func_name}",
                summary=tool_summary,
                data=tool_execution.data,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": func_name,
                "content": tool_execution.model_output,
            })

    def _summarize_tool_result(self, name: str, tool_result: str) -> str:
        try:
            parsed = json.loads(tool_result)
            if isinstance(parsed, dict):
                if parsed.get("error"): return f"执行失败：{parsed['error']}"
                if name == "get_log_context":
                    line_no = parsed.get("representative_line")
                    if line_no: return f"已返回代表行 #{line_no} 的日志上下文"
                    return "已返回目标日志的上下文"
                if name == "get_active_mod_list":
                    return f"已返回 {parsed.get('total_active', 0)} 个激活模组"
                if name == "search_mods":
                    return f"已找到 {len(parsed.get('matched', []) or [])} 个候选模组"
                if name == "get_mod_info":
                    data = parsed.get("data", {}) if isinstance(parsed.get("data"), dict) else {}
                    return f"已返回模组元数据：{data.get('name') or parsed.get('package_id') or '未知模组'}"
                if name == "get_mod_rules":
                    return "已返回模组规则信息"
                if name == "get_mod_user_data":
                    return "已返回模组的用户备注/标签/分组信息"
                if name == "get_group_mods":
                    return f"已返回 {len(parsed.get('matched_groups', []) or [])} 个匹配分组"
        except Exception:
            pass

        safe_text = (tool_result or "").replace("\r", " ").replace("\n", " ").strip()
        if not safe_text: return "工具执行完成，但没有返回可展示内容"
        return safe_text[:180] + ("..." if len(safe_text) > 180 else "")

    def _parse_final_text(
        self,
        final_text: str,
        final_think: str = "",
        *,
        assistant: AssistantDefinition | None = None,
    ) -> dict[str, Any]:
        normalized_text = str(final_text or "").strip()

        clean_text = normalized_text
        parsed_actions: list[dict[str, Any]] = []
        structured_output = None
        last_structured_error: ValidationError | None = None
        selected_structured_error: ValidationError | None = None
        selected_candidate_source = ""
        selected_candidate_index = -1
        selected_parse_mode = ""
        action_normalization = self._create_action_normalization_debug()
        candidate_entries = self._collect_structured_output_candidates(normalized_text)
        for candidate_index, candidate_entry in enumerate(candidate_entries):
            candidate_text = candidate_entry.get("text", "")
            structured_output, candidate_error = self._parse_structured_output(
                "assistant_response",
                candidate_text,
                log_failure=False,
            )
            current_parse_mode = "validated_json" if isinstance(structured_output, dict) else ""
            if candidate_error is not None:
                last_structured_error = candidate_error
            if not isinstance(structured_output, dict):
                repaired_output = self._extract_json_from_text(candidate_text)
                current_parse_mode = "repair_json" if isinstance(repaired_output, dict) else ""
                structured_output = repaired_output if isinstance(repaired_output, dict) else None
            if isinstance(structured_output, dict):
                selected_candidate_source = str(candidate_entry.get("source") or "")
                selected_candidate_index = candidate_index
                selected_parse_mode = current_parse_mode or "validated_json"
                selected_structured_error = candidate_error if selected_parse_mode == "repair_json" else None
                if selected_structured_error is not None:
                    logger.warning(
                        "[AI结构化输出] 严格 JSON 校验失败，已使用 repair_json 兜底 "
                        f"task=assistant_response source={selected_candidate_source} "
                        f"index={selected_candidate_index}: {selected_structured_error}"
                    )
                break
        if not isinstance(structured_output, dict) and last_structured_error is not None:
            logger.warning(f"[AI结构化输出] 校验失败 task=assistant_response: {last_structured_error}")
        if isinstance(structured_output, dict):
            analysis_text = str(structured_output.get("analysis") or structured_output.get("text") or "").strip()
            if analysis_text:
                clean_text = analysis_text
            parsed_actions, action_normalization = self._normalize_ai_actions(
                structured_output.get("actions", []),
                self._get_allowed_action_types(assistant),
            )

        lines = clean_text.splitlines()
        while lines:
            last_line = lines[-1].strip()
            if last_line == "" or re.search(r'^[-~\s]*$', last_line):
                lines.pop()
            else:
                break
        clean_text = "\n".join(lines)

        if not clean_text.strip():
            if final_think.strip():
                clean_text = (
                    "⚠️ **AI 已耗尽最大输出长度限制，未能生成最终结论。**\n\n"
                    "<details><summary>点击查看 AI 的深度思考过程</summary>\n\n"
                    "```text\n"
                    + final_think
                    + "\n```\n</details>"
                )
            else:
                clean_text = "⚠️ **AI 未能生成有效的回答。** 可能是由于 API 超时、网络拦截或模型不支持导致的空白返回。"

        return {
            "analysis": clean_text,
            "actions": parsed_actions,
            "_trace_debug": {
                "raw_model_output": normalized_text,
                "structured_output_debug": {
                    "used_structured_output": isinstance(structured_output, dict),
                    "candidate_count": len(candidate_entries),
                    "selected_candidate_source": selected_candidate_source,
                    "selected_candidate_index": selected_candidate_index,
                    "parse_mode": selected_parse_mode,
                    "validation_error": str(selected_structured_error) if selected_structured_error is not None else "",
                },
                "action_normalization": action_normalization,
            },
        }

    def _collect_structured_output_candidates(self, text: str) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        seen: set[str] = set()

        def add_candidate(raw_text: Any, source: str) -> None:
            """按来源登记候选 JSON 文本，并去重保留最早来源。"""
            candidate = str(raw_text or "").strip()
            if not candidate or candidate in seen: return
            seen.add(candidate)
            candidates.append({
                "source": str(source or "").strip(),
                "text": candidate,
            })

        normalized_text = str(text or "").strip()
        if not normalized_text: return []

        sanitized_text = re.sub(r'^[-\s]*```json\s*', '', normalized_text, flags=re.IGNORECASE)
        sanitized_text = re.sub(r'^[-\s]*```\s*', '', sanitized_text)
        sanitized_text = re.sub(r'```\s*$', '', sanitized_text).strip()

        for block in self._extract_balanced_json_fragments(normalized_text):
            add_candidate(block, "balanced_json")

        fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", normalized_text, flags=re.IGNORECASE)
        for block in fenced_blocks:
            add_candidate(block, "fenced_json")

        add_candidate(sanitized_text, "sanitized_text")
        add_candidate(normalized_text, "raw_text")

        return candidates

    def _extract_balanced_json_fragments(self, text: str) -> list[str]:
        fragments: list[str] = []
        stack: list[str] = []
        start_index: int | None = None
        in_string = False
        escape_next = False

        closing_map = {"{": "}", "[": "]"}
        opening_tokens = set(closing_map.keys())
        closing_tokens = set(closing_map.values())

        for index, char in enumerate(str(text or "")):
            if escape_next:
                escape_next = False
                continue
            if char == "\\" and in_string:
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if char in opening_tokens:
                if not stack:
                    start_index = index
                stack.append(char)
                continue

            if char in closing_tokens and stack:
                expected = closing_map.get(stack[-1])
                if char != expected:
                    stack.clear()
                    start_index = None
                    continue
                stack.pop()
                if not stack and start_index is not None:
                    fragments.append(text[start_index:index + 1])
                    start_index = None

        return fragments

    def _extract_json_from_text(self, text: str, is_batch: bool = False):
        try:
            parsed = repair_json(text, return_objects=True)
            if isinstance(parsed, dict):
                return [parsed] if is_batch else parsed
            if isinstance(parsed, list):
                return parsed
            return None
        except Exception as exc:
            logger.debug(f"JSON Repair 失败，已退回普通文本路径: {exc}")
            return None

    def _parse_structured_output(self, task_key: str, text: str, *, log_failure: bool = True) -> tuple[Any, ValidationError | None]:
        """对结构化输出做最小必要校验。"""
        adapter_map = {
            "assistant_response": TypeAdapter(AIAssistantResponseEnvelope),
        }
        adapter = adapter_map.get(task_key)
        if adapter is None:
            return self._extract_json_from_text(text), None
        try:
            parsed = adapter.validate_json(text)
            return (parsed.model_dump() if hasattr(parsed, "model_dump") else parsed), None
        except ValidationError as exc:
            if log_failure:
                logger.warning(f"[AI结构化输出] 校验失败 task={task_key}: {exc}")
            return self._extract_json_from_text(text), exc

    def _get_allowed_action_types(self, assistant: AssistantDefinition | None) -> list[str]:
        return get_allowed_action_types(
            assistant,
            getattr(getattr(self, "definition_manager", None), "action_definitions", {}) or {},
        )

    def _build_assistant_output_contract(self, assistant: AssistantDefinition) -> str:
        return build_assistant_output_contract(
            assistant,
            getattr(getattr(self, "definition_manager", None), "action_definitions", {}) or {},
        )

    def _create_action_normalization_debug(self) -> dict[str, Any]:
        from backend.ai.def_actions import create_action_normalization_debug

        return create_action_normalization_debug()

    def _normalize_ai_actions(
        self,
        raw_actions: Any,
        allowed_action_types: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return normalize_ai_actions(
            raw_actions,
            action_definitions=getattr(self.definition_manager, "action_definitions", {}) or {},
            allowed_action_types=allowed_action_types,
        )

    def _build_error_response(self, error: Exception, token_usage: dict[str, Any], summary_label: str = "点击展开诊断建议") -> dict[str, Any]:
        import traceback

        token_usage["estimated_total_tokens"] = (
            token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
        )
        error_trace = traceback.format_exc()
        error_markdown = (
            "**AI 请求没有完成。**\n\n"
            "常见原因包括：模型服务暂时无响应、网络或代理连接中断、API Key 无效、当前模型不支持本次工具调用，"
            "或中转服务返回了不兼容的响应。\n\n"
            f"<details><summary>{summary_label}</summary>\n\n"
            "请先检查 AI 设置里的模型、Base URL、API Key 和代理配置；如果刚才请求内容较大，"
            "可以减少附件或稍后重试。详细技术错误已写入系统日志。\n"
            "</details>"
        )
        return {
            "analysis": error_markdown,
            "actions": [],
            "token_usage": token_usage,
            "message_usage": self._build_message_usage_from_request(token_usage),
            "detail": {
                "original_error": str(error),
                "traceback": error_trace,
            },
        }

    def _build_forced_summary(
        self,
        session_id: str,
        messages: list[dict],
        llm_kwargs: dict,
        model_name: str,
        token_usage: dict[str, Any],
        assistant: AssistantDefinition,
        prompt_input_breakdown: dict[str, Any] | None = None,
        accumulated_prompt_input_breakdown: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger.warning(f"[AI会话] 工具轮达到上限，转入强制总结 session_id={session_id}")
        token_usage["forced_final_round"] = True
        forced_system_text = (
            "你已经完成资料查阅。禁止继续调用任何工具。\n"
            "请直接基于当前证据给出最终回答；如果证据仍不足，也要明确给出最可能的 1-3 个原因、"
            "证据依据，以及下一步建议用户如何验证。"
        )
        forced_messages = messages + [{
            "role": "system",
            "content": forced_system_text,
        }]

        try:
            prompt_tokens_this_round = self._estimate_messages_tokens(forced_messages, model_name)
            token_usage["estimated_prompt_tokens"] += prompt_tokens_this_round
            forced_round_prompt_input_breakdown = self._build_prompt_input_breakdown_for_round(
                prompt_tokens_this_round=prompt_tokens_this_round,
                base_prompt_tokens=int((prompt_input_breakdown or {}).get("total_tokens", 0) or 0),
                base_prompt_breakdown=prompt_input_breakdown or create_prompt_input_breakdown(),
                model_name=model_name,
                forced_summary_text=forced_system_text,
            )
            accumulated_prompt_input_breakdown = self._merge_prompt_input_breakdown(
                accumulated_prompt_input_breakdown or create_prompt_input_breakdown(),
                forced_round_prompt_input_breakdown,
            )
            stream_result = self._run_completion_with_fallback(
                messages=forced_messages,
                llm_kwargs=llm_kwargs,
                session_id=session_id,
                tools=None,
                tool_choice=None,
            )
            reasoning_text = str(stream_result.get("final_think") or "")
            answer_output_tk = self._estimate_text_tokens(stream_result["final_text"], model_name)
            reasoning_output_tk = self._estimate_text_tokens(reasoning_text, model_name) if reasoning_text else 0
            token_usage["estimated_answer_completion_tokens"] += answer_output_tk
            token_usage["estimated_reasoning_completion_tokens"] += reasoning_output_tk
            token_usage["estimated_completion_tokens"] += answer_output_tk + reasoning_output_tk
            token_usage["estimated_total_tokens"] = (
                token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
            )

            final_response = self._parse_final_text(
                stream_result["final_text"],
                stream_result.get("final_think", ""),
                assistant=assistant,
            )
            final_response["warnings"] = list(stream_result.get("warnings") or [])
            final_response["reasoning_content"] = reasoning_text
            if not final_response.get("analysis"):
                final_response["analysis"] = "AI 已完成查证，但没有生成有效总结文本。建议查看上方工具步骤详情，优先核对关键上下文。"
            final_response["message_usage"] = self._build_message_usage_from_request(token_usage)
            final_response["token_usage"] = token_usage
            final_response["prompt_input_breakdown"] = accumulated_prompt_input_breakdown
            return final_response
        except AssistantRequestCancelled:
            raise
        except Exception as exc:
            logger.error(
                "AI 会话强制总结失败。session_id=%s",
                session_id,
                extra={"error_code": "AI.SESSION.FORCED_SUMMARY_FAILED", "extra_context": {"session_id": session_id, "original_error": str(exc)}},
                exc_info=True,
            )
            return self._build_error_response(exc, token_usage, "点击展开诊断建议")
