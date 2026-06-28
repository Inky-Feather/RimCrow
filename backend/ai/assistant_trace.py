"""Assistant 会话 trace 存储。

把 trace 的创建、收尾和会话聚合从 `AIManager` 中拆出来，
让 assistant 运行时只关心“何时记录什么”，不再关心“如何归档和汇总”。
"""

from __future__ import annotations

import uuid
from threading import Lock
from typing import Any

from backend.ai.ai_contracts import (
    ConversationTraceSession,
    MessageTokenUsage,
    PromptInputBreakdown,
    RequestMessageUsage,
    RequestTraceRecord,
    RequestTraceTokenUsage,
    ResolvedContextAttachment,
)
from backend.utils.tools import current_ms


class AssistantTraceStore:
    """内存态 assistant trace 存储。"""

    def __init__(self, limit: int = 200):
        self._limit = max(20, int(limit or 200))
        self._records_by_session: dict[str, list[RequestTraceRecord]] = {}
        self._index: list[RequestTraceRecord] = []
        self._lock = Lock()

    def create_record(
        self,
        *,
        session_id: str,
        assistant_id: str,
        owner_type: str,
        owner_key: str,
        prompt_id: str,
        model: str,
        user_input_text: str,
        messages_snapshot: list[dict[str, Any]] | None = None,
        request_payload: dict[str, Any] | None = None,
        raw_attachments: list[dict[str, Any]] | None = None,
        resolved_attachments: list[ResolvedContextAttachment] | None = None,
    ) -> RequestTraceRecord:
        """为单轮助手请求创建 trace 记录并挂到所属会话下。"""
        record = RequestTraceRecord(
            trace_id=str(uuid.uuid4()),
            session_id=session_id,
            assistant_id=assistant_id,
            owner_type=owner_type,
            owner_key=owner_key,
            prompt_id=prompt_id,
            model=model,
            started_at=current_ms(),
            user_input_text=user_input_text,
            messages_snapshot=list(messages_snapshot or []),
            request_payload=dict(request_payload or {}),
            raw_attachments=list(raw_attachments or []),
            resolved_attachments=list(resolved_attachments or []),
        )
        with self._lock:
            session_records = self._records_by_session.setdefault(session_id, [])
            session_records.append(record)
            self._index.append(record)
            if len(self._index) > self._limit:
                removed = self._index.pop(0)
                removed_records = self._records_by_session.get(removed.session_id, [])
                self._records_by_session[removed.session_id] = [
                    item for item in removed_records if item.trace_id != removed.trace_id
                ]
                if not self._records_by_session[removed.session_id]:
                    self._records_by_session.pop(removed.session_id, None)
        return record

    def finalize_record(
        self,
        record: RequestTraceRecord | None,
        *,
        status: str,
        final_output: str = "",
        final_reasoning: str = "",
        token_usage: dict[str, Any] | None = None,
        message_usage: dict[str, Any] | None = None,
        prompt_input_breakdown: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        """在请求结束时补齐 trace 的结果、统计与错误信息。"""
        if record is None: return
        record.finished_at = current_ms()
        record.status = status
        if final_output:
            record.final_output = final_output
        if final_reasoning:
            record.final_reasoning = final_reasoning
        if response_payload:
            record.response_payload = dict(response_payload)
        record.error = error
        if token_usage:
            record.token_usage = RequestTraceTokenUsage(
                prompt_tokens=int(token_usage.get("estimated_prompt_tokens", 0) or 0),
                completion_tokens=int(token_usage.get("estimated_completion_tokens", 0) or 0),
                total_tokens=int(token_usage.get("estimated_total_tokens", 0) or 0),
                tool_rounds=int(token_usage.get("tool_rounds", 0) or 0),
                answer_completion_tokens=int(token_usage.get("estimated_answer_completion_tokens", 0) or 0),
                reasoning_completion_tokens=int(token_usage.get("estimated_reasoning_completion_tokens", 0) or 0),
                tool_call_completion_tokens=int(token_usage.get("estimated_tool_call_completion_tokens", 0) or 0),
            )
        if message_usage:
            record.message_usage = RequestMessageUsage.model_validate(message_usage)
        if prompt_input_breakdown:
            record.prompt_input_breakdown = PromptInputBreakdown.model_validate(prompt_input_breakdown)

    def get_trace_records(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """按会话返回 trace 快照；不指定会话时返回最近所有会话。"""
        with self._lock:
            if session_id:
                records = list(self._records_by_session.get(session_id, []))
                if not records: return []
                return [self._build_session_snapshot(session_id, records).model_dump()]

            sessions: list[ConversationTraceSession] = []
            for current_session_id, records in self._records_by_session.items():
                if not records:
                    continue
                sessions.append(self._build_session_snapshot(current_session_id, list(records)))
            sessions.sort(key=lambda item: int(item.started_at or 0), reverse=True)
            return [session.model_dump() for session in sessions]

    def _build_session_snapshot(
        self,
        session_id: str,
        records: list[RequestTraceRecord],
    ) -> ConversationTraceSession:
        ordered_records = sorted(records, key=lambda item: int(item.started_at or 0))
        first_record = ordered_records[0]
        last_record = ordered_records[-1]
        total_usage = RequestTraceTokenUsage(
            prompt_tokens=sum(int(item.token_usage.prompt_tokens or 0) for item in ordered_records),
            completion_tokens=sum(int(item.token_usage.completion_tokens or 0) for item in ordered_records),
            total_tokens=sum(int(item.token_usage.total_tokens or 0) for item in ordered_records),
            tool_rounds=sum(int(item.token_usage.tool_rounds or 0) for item in ordered_records),
            answer_completion_tokens=sum(int(item.token_usage.answer_completion_tokens or 0) for item in ordered_records),
            reasoning_completion_tokens=sum(int(item.token_usage.reasoning_completion_tokens or 0) for item in ordered_records),
            tool_call_completion_tokens=sum(int(item.token_usage.tool_call_completion_tokens or 0) for item in ordered_records),
        )
        total_message_usage = RequestMessageUsage(
            user=MessageTokenUsage(
                prompt_tokens=sum(int(item.message_usage.user.prompt_tokens or 0) for item in ordered_records),
                completion_tokens=sum(int(item.message_usage.user.completion_tokens or 0) for item in ordered_records),
                total_tokens=sum(int(item.message_usage.user.total_tokens or 0) for item in ordered_records),
            ),
            assistant=MessageTokenUsage(
                prompt_tokens=sum(int(item.message_usage.assistant.prompt_tokens or 0) for item in ordered_records),
                completion_tokens=sum(int(item.message_usage.assistant.completion_tokens or 0) for item in ordered_records),
                total_tokens=sum(int(item.message_usage.assistant.total_tokens or 0) for item in ordered_records),
            ),
        )
        total_prompt_input_breakdown = PromptInputBreakdown(
            total_tokens=sum(int(item.prompt_input_breakdown.total_tokens or 0) for item in ordered_records),
            prompt_template_tokens=sum(int(item.prompt_input_breakdown.prompt_template_tokens or 0) for item in ordered_records),
            memory_tokens=sum(int(item.prompt_input_breakdown.memory_tokens or 0) for item in ordered_records),
            attachment_tokens=sum(int(item.prompt_input_breakdown.attachment_tokens or 0) for item in ordered_records),
            user_input_tokens=sum(int(item.prompt_input_breakdown.user_input_tokens or 0) for item in ordered_records),
            tool_context_tokens=sum(int(item.prompt_input_breakdown.tool_context_tokens or 0) for item in ordered_records),
            forced_summary_tokens=sum(int(item.prompt_input_breakdown.forced_summary_tokens or 0) for item in ordered_records),
        )

        latest_question = str(last_record.user_input_text or first_record.user_input_text or "").strip()
        title = latest_question[:60] if latest_question else (
            first_record.assistant_id or first_record.prompt_id or session_id
        )
        statuses = [str(item.status or "") for item in ordered_records]
        if any(status == "error" for status in statuses):
            session_status = "error"
        elif any(status == "cancelled" for status in statuses):
            session_status = "cancelled"
        elif statuses and all(status == "done" for status in statuses):
            session_status = "done"
        else:
            session_status = statuses[-1] if statuses else "running"

        return ConversationTraceSession(
            session_id=session_id,
            assistant_id=first_record.assistant_id,
            owner_type=first_record.owner_type,
            owner_key=first_record.owner_key,
            title=title,
            status=session_status,
            started_at=int(first_record.started_at or 0),
            finished_at=last_record.finished_at,
            trace_count=len(ordered_records),
            request_count=len(ordered_records),
            total_token_usage=total_usage,
            total_message_usage=total_message_usage,
            total_prompt_input_breakdown=total_prompt_input_breakdown,
            traces=[record.model_copy(deep=True) for record in ordered_records],
        )
