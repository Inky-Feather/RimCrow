import unittest
import json
import sys
import types
from types import SimpleNamespace

try:
    import json_repair  # noqa: F401
except ModuleNotFoundError:
    json_repair_stub = types.ModuleType("json_repair")
    json_repair_stub.repair_json = lambda text, return_objects=False: json.loads(text)
    sys.modules["json_repair"] = json_repair_stub

tools_stub = types.ModuleType("backend.ai.ai_tools")


class ToolExecutionResultStub:
    def __init__(self, name="", ok=True, model_output="{}", data=None, summary="", error=""):
        self.name = name
        self.ok = ok
        self.model_output = model_output
        self.data = data or {}
        self.summary = summary
        self.error = error


class AIToolExecutorStub:
    def __init__(self, *args, **kwargs):
        pass

    def get_tool_schemas(self, tool_names=None):
        return [
            {"type": "function", "function": {"name": name, "description": name, "parameters": {}}}
            for name in (tool_names or [])
        ]

    def build_tool_call_display(self, func_name, func_args):
        return {
            "display_name": func_name,
            "arguments_preview": func_args,
            "arguments_pretty": func_args,
        }

    def execute_structured(self, func_name, func_args):
        return ToolExecutionResultStub(name=func_name)

    def build_tool_result_display(self, tool_execution):
        return {
            "display_name": getattr(tool_execution, "name", "") or "tool",
            "result_pretty": getattr(tool_execution, "model_output", "") or "{}",
        }


tools_stub.AIToolExecutor = AIToolExecutorStub
tools_stub.ToolExecutionResult = ToolExecutionResultStub
original_ai_tools_module = sys.modules.get("backend.ai.ai_tools")
sys.modules["backend.ai.ai_tools"] = tools_stub

import backend.ai.assistant_runtime as assistant_runtime_module
from backend.ai.assistant_runtime import AssistantRuntime

if original_ai_tools_module is None:
    sys.modules.pop("backend.ai.ai_tools", None)
else:
    sys.modules["backend.ai.ai_tools"] = original_ai_tools_module


class AIDefinitionManagerStub:
    def __init__(self):
        self.assistants = {
            "assistant.demo": {
                "id": "assistant.demo",
                "name": "Demo",
                "description": "demo",
                "prompt_id": "demo_prompt",
                "tool_scope_selectable": [],
                "action_types": [],
            },
            "assistant.demo_actions": {
                "id": "assistant.demo_actions",
                "name": "Demo Actions",
                "description": "demo with actions",
                "prompt_id": "demo_prompt",
                "tool_scope_selectable": [],
                "action_types": ["MOD_STATE"],
            },
            "assistant.log_game": {
                "id": "assistant.log_game",
                "name": "Game Log",
                "description": "game log assistant",
                "prompt_id": "demo_prompt",
                "tool_scope_selectable": [],
                "action_types": [],
            },
        }
        self.action_definitions = {
            "MOD_STATE": {
                "type": "MOD_STATE",
                "label": "模组启用状态",
                "description": "调整一个或多个模组的启用状态。",
                "payload_schema": {
                    "format": {
                        "type": "MOD_STATE",
                        "variant": "enable or disable",
                        "payload": {"mod_ids": ["package.id"]},
                    },
                    "when": "当一个或多个 package_id 和启用/停用方向已经明确时输出；无需额外目标对象。",
                    "examples": [
                        {"type": "MOD_STATE", "variant": "enable", "payload": {"mod_ids": ["demo.mod"]}},
                    ],
                    "notes": [
                        "enable 表示把这些模组加入启用列表。",
                    ],
                },
                "variants": {
                    "enable": {
                        "label": "模组启用状态",
                        "title": "启用模组",
                        "description": "建议将这些模组调整为启用状态。",
                    },
                    "disable": {
                        "label": "模组启用状态",
                        "title": "停用模组",
                        "description": "建议将这些模组调整为停用状态。",
                    },
                },
            },
        }
        self.prompts = {
            "demo_prompt": {
                "category": "assistant",
                "system": "SYSTEM {message}",
                "user_template": "USER {message}",
            }
        }
        self.attachment_definitions = {}

    def get_attachment_projection_fields(self, kind, prompt_id=None, options=None):
        return []


class LlmStub:
    def __init__(self):
        self.completion_calls = 0

    def build_kwargs(self, override_config=None):
        return {"model": "test-model"}

    def estimate_text_tokens(self, text, model_name):
        return len(text)

    def estimate_messages_tokens(self, messages, model_name):
        return sum(len(str(message.get("content", ""))) for message in messages)

    def _message_text(self, content):
        return str(content or "")

    def completion(self, messages=None, llm_kwargs=None, stream=False, tools=None, tool_choice=None):
        self.completion_calls += 1
        joined_content = "\n".join(str(message.get("content", "")) for message in (messages or []))
        response_text = (
            '{"analysis":"hello","actions":[{"type":"MOD_STATE","variant":"disable","payload":{"mod_ids":["demo.mod"]}}]}'
            if "MOD_STATE" in joined_content
            else '{"analysis":"hello"}'
        )
        if not stream:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=response_text, reasoning_content=""),
                    )
                ]
            )

        def generator():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=response_text, reasoning_content=None, tool_calls=None),
                    )
                ]
            )

        return generator()


class StreamingJsonLlmStub(LlmStub):
    def completion(self, messages=None, llm_kwargs=None, stream=False, tools=None, tool_choice=None):
        response_chunks = [
            '{"analysis":"第一行',
            '\\n第二行',
            '，包含\\"引号\\"',
            '","actions":[{"type":"MOD_STATE","variant":"disable","payload":{"mod_ids":["demo.mod"]}}]}',
        ]
        if not stream:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="".join(response_chunks), reasoning_content=""),
                    )
                ]
            )

        def generator():
            for chunk in response_chunks:
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=chunk, reasoning_content=None, tool_calls=None),
                        )
                    ]
                )

        return generator()


class ReasoningFieldLlmStub(LlmStub):
    def completion(self, messages=None, llm_kwargs=None, stream=False, tools=None, tool_choice=None):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"analysis":"hello"}', reasoning="vllm trace"),
                )
            ]
        )


class InlineThinkLlmStub(LlmStub):
    def completion(self, messages=None, llm_kwargs=None, stream=False, tools=None, tool_choice=None):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='<think>local trace</think>{"analysis":"hello"}'),
                )
            ]
        )


class ToolUnsupportedThenStreamingLlmStub(LlmStub):
    def __init__(self):
        super().__init__()
        self.calls = []

    def completion(self, messages=None, llm_kwargs=None, stream=False, tools=None, tool_choice=None):
        self.completion_calls += 1
        self.calls.append({
            "stream": stream,
            "tools": tools,
            "tool_choice": tool_choice,
            "messages": list(messages or []),
        })
        if tools is not None:
            raise Exception('Ollama_chatException - {"error":"model does not support tools"}')
        if messages and str(messages[-1].get("role") or "") == "system":
            raise Exception('Ollama_chatException - {"error":"Failed to create new sequence: no input provided"}')

        def generator():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content='{"analysis":"fallback"}', reasoning_content=None, tool_calls=None),
                    )
                ]
            )

        return generator()


class TestAssistantRuntime(unittest.TestCase):
    def test_run_session_records_single_trace(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        result = runtime.run_session(
            {"assistant_id": "assistant.demo", "question": "hi", "history": [], "attachments": []},
            active_context=None,
            reader=None,
        )

        self.assertEqual(result["analysis"], "hello")
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["token_usage"]["model"], "test-model")
        self.assertEqual(result["message_usage"]["user"]["total_tokens"], result["token_usage"]["estimated_prompt_tokens"])
        self.assertEqual(result["message_usage"]["assistant"]["total_tokens"], result["token_usage"]["estimated_completion_tokens"])
        self.assertEqual(
            result["session_usage_summary"]["request_usage"]["total_tokens"],
            result["token_usage"]["estimated_total_tokens"],
        )

        sessions = runtime.get_trace_records()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["trace_count"], 1)
        self.assertEqual(sessions[0]["assistant_id"], "assistant.demo")

    def test_get_trace_records_by_session_id(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        payload = {"assistant_id": "assistant.demo", "question": "hi", "history": [], "attachments": []}

        runtime.run_session(payload, active_context=None, reader=None)
        session_id = runtime.get_trace_records()[0]["session_id"]

        session_records = runtime.get_trace_records(session_id)

        self.assertEqual(len(session_records), 1)
        self.assertEqual(session_records[0]["session_id"], session_id)
        self.assertEqual(session_records[0]["request_count"], 1)

    def test_runtime_keeps_session_memory_without_frontend_history_replay(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        first_result = runtime.run_session(
            {"session_id": "session-demo", "assistant_id": "assistant.demo", "question": "first", "history": [], "attachments": []},
            active_context=None,
            reader=None,
        )
        second_result = runtime.run_session(
            {"session_id": "session-demo", "assistant_id": "assistant.demo", "question": "second", "history": [], "attachments": []},
            active_context=None,
            reader=None,
        )

        self.assertEqual(first_result["analysis"], "hello")
        self.assertEqual(second_result["analysis"], "hello")

        traces = runtime.get_trace_records("session-demo")
        self.assertEqual(len(traces), 1)
        trace_items = traces[0]["traces"]
        self.assertEqual(len(trace_items), 2)
        second_messages = trace_items[1]["messages_snapshot"]
        second_contents = [str(item.get("content", "")) for item in second_messages]
        self.assertTrue(any("first" in content for content in second_contents))
        self.assertTrue(any("hello" in content for content in second_contents))

    def test_complete_without_stream_reads_reasoning_field(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), ReasoningFieldLlmStub())

        result = runtime._complete_without_stream(
            messages=[{"role": "user", "content": "hi"}],
            llm_kwargs={"model": "test-model"},
        )

        self.assertEqual(result["final_text"], '{"analysis":"hello"}')
        self.assertEqual(result["final_think"], "vllm trace")

    def test_complete_without_stream_extracts_inline_think_block(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), InlineThinkLlmStub())

        result = runtime._complete_without_stream(
            messages=[{"role": "user", "content": "hi"}],
            llm_kwargs={"model": "test-model"},
        )

        self.assertEqual(result["final_text"], '{"analysis":"hello"}')
        self.assertEqual(result["final_think"], "local trace")

    def test_runtime_accepts_canonical_assistant_context_request(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        result = runtime.run_session(
            {
                "session_id": "session-canonical",
                "assistant_context": {
                    "assistant_id": "assistant.demo",
                    "owner_type": "assistant",
                    "owner_key": "demo",
                    "request_payload": {
                        "question": "hi from canonical",
                        "attachments": [],
                        "enabled_tools": [],
                        "ai_override_config": {},
                    },
                },
            },
            active_context=None,
            reader=None,
        )

        self.assertEqual(result["analysis"], "hello")
        trace_session = runtime.get_trace_records("session-canonical")[0]
        self.assertEqual(trace_session["traces"][0]["user_input_text"], "hi from canonical")

    def test_normalize_ai_actions_uses_variant_metadata_for_title_and_description(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        actions, diagnostics = runtime._normalize_ai_actions([{
            "type": "MOD_STATE",
            "variant": "disable",
            "payload": {"mod_ids": ["demo.mod"]},
            "title": "模型自定义标题",
            "description": "模型自定义说明",
        }], ["MOD_STATE"])

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["title"], "停用模组")
        self.assertEqual(actions[0]["description"], "建议将这些模组调整为停用状态。")
        self.assertEqual(diagnostics["normalized_breakdown"]["MOD_STATE.disable"], 1)

    def test_assistant_output_contract_includes_action_trigger_examples(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        assistant = assistant_runtime_module.AssistantDefinition.model_validate(
            runtime.definition_manager.assistants["assistant.demo_actions"]
        )

        contract = runtime._build_assistant_output_contract(assistant)

        self.assertIn("触发条件", contract)
        self.assertIn("无需额外目标对象", contract)
        self.assertIn('"variant": "enable"', contract)
        self.assertIn("enable 表示把这些模组加入启用列表", contract)

    def test_runtime_injects_default_question_for_log_attachments(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        runtime.run_session(
            {
                "session_id": "session-log",
                "assistant_id": "assistant.log_game",
                "question": "",
                "attachments": [
                    {
                        "kind": "diagnosis_context",
                        "selector": {"mode": "summary"},
                    }
                ],
            },
            active_context=None,
            reader=None,
        )

        trace_session = runtime.get_trace_records("session-log")[0]
        self.assertEqual(
            trace_session["traces"][0]["user_input_text"],
            "请深度分析我提交的日志数据，并给出修复建议。",
        )

    def test_trace_session_contains_backend_timeline_items(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        runtime.run_session(
            {"session_id": "session-trace", "assistant_id": "assistant.demo", "question": "hi", "attachments": []},
            active_context=None,
            reader=None,
        )

        trace_session = runtime.get_trace_records("session-trace")[0]
        timeline_items = trace_session["timeline_items"]

        self.assertEqual(len(timeline_items), 2)
        self.assertEqual(timeline_items[0]["kind"], "request")
        self.assertEqual(timeline_items[1]["kind"], "response")
        self.assertIn("runtime", trace_session)

    def test_runtime_returns_actions_in_main_response(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        result = runtime.run_session(
            {
                "session_id": "session-actions",
                "assistant_id": "assistant.demo_actions",
                "question": "plan actions",
                "history": [],
                "attachments": [],
            },
            active_context=None,
            reader=None,
        )

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["type"], "MOD_STATE")
        self.assertEqual(
            result["message_usage"]["assistant"]["total_tokens"],
            result["token_usage"]["estimated_completion_tokens"],
        )

        trace_session = runtime.get_trace_records("session-actions")[0]
        self.assertEqual(trace_session["runtime"]["evidence_count"], 0)
        self.assertFalse(any(item["kind"] == "planning" for item in trace_session["timeline_items"]))
        self.assertEqual(trace_session["traces"][0]["response_payload"]["actions"][0]["type"], "MOD_STATE")
        self.assertEqual(
            trace_session["total_message_usage"]["user"]["total_tokens"],
            trace_session["total_token_usage"]["prompt_tokens"],
        )

    def test_run_session_trace_records_raw_output_and_action_diagnostics(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        result = runtime.run_session(
            {
                "session_id": "session-action-debug",
                "assistant_id": "assistant.demo_actions",
                "question": "plan actions",
                "history": [],
                "attachments": [],
            },
            active_context=None,
            reader=None,
        )

        self.assertNotIn("_trace_debug", result)
        trace_response = runtime.get_trace_records("session-action-debug")[0]["traces"][0]["response_payload"]
        self.assertTrue(str(trace_response["raw_model_output"]).startswith("{"))
        self.assertTrue(trace_response["structured_output_debug"]["used_structured_output"])
        self.assertEqual(trace_response["action_normalization"]["input_count"], 1)
        self.assertEqual(trace_response["action_normalization"]["normalized_count"], 1)
        self.assertEqual(trace_response["action_normalization"]["normalized_breakdown"]["MOD_STATE.disable"], 1)

    def test_parse_final_text_accepts_fenced_json_response(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        assistant = assistant_runtime_module.AssistantDefinition.model_validate(
            runtime.definition_manager.assistants["assistant.demo_actions"]
        )

        parsed = runtime._parse_final_text(
            '```json\n{"analysis":"fenced","actions":[{"type":"MOD_STATE","variant":"disable","payload":{"mod_ids":["demo.mod"]}}]}\n```',
            assistant=assistant,
        )

        self.assertEqual(parsed["analysis"], "fenced")
        self.assertEqual(len(parsed["actions"]), 1)
        self.assertEqual(parsed["actions"][0]["type"], "MOD_STATE")

    def test_parse_final_text_accepts_fenced_json_with_nested_markdown_fence(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        assistant = assistant_runtime_module.AssistantDefinition.model_validate(
            runtime.definition_manager.assistants["assistant.demo_actions"]
        )

        parsed = runtime._parse_final_text(
            '现在可以诊断。\n\n```json\n{'
            '"analysis":"证据：\\n```xml\\n<li Class=\\"Apparel\\">x</li>\\n```\\n结论",'
            '"actions":[{"type":"MOD_STATE","variant":"enable","payload":{"mod_ids":["zal.darknet"]}}]'
            '}\n```',
            assistant=assistant,
        )

        self.assertIn('```xml', parsed["analysis"])
        self.assertEqual(len(parsed["actions"]), 1)
        self.assertEqual(parsed["actions"][0]["payload"]["mod_ids"], ["zal.darknet"])
        self.assertEqual(
            parsed["_trace_debug"]["structured_output_debug"]["selected_candidate_source"],
            "balanced_json",
        )
        self.assertEqual(parsed["_trace_debug"]["structured_output_debug"]["validation_error"], "")

    def test_parse_final_text_accepts_json_wrapped_by_extra_text(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        assistant = assistant_runtime_module.AssistantDefinition.model_validate(
            runtime.definition_manager.assistants["assistant.demo_actions"]
        )

        parsed = runtime._parse_final_text(
            '下面是最终结果：\n{"analysis":"wrapped","actions":[{"type":"MOD_STATE","variant":"disable","payload":{"mod_ids":["demo.mod"]}}]}\n请查收。',
            assistant=assistant,
        )

        self.assertEqual(parsed["analysis"], "wrapped")
        self.assertEqual(len(parsed["actions"]), 1)
        self.assertEqual(parsed["actions"][0]["variant"], "disable")

    def test_parse_final_text_keeps_analysis_when_actions_partially_invalid(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        assistant = assistant_runtime_module.AssistantDefinition.model_validate(
            runtime.definition_manager.assistants["assistant.demo_actions"]
        )

        parsed = runtime._parse_final_text(
            '{"analysis":"keep-analysis","actions":[{"type":"MOD_STATE","variant":"disable","payload":{"mod_ids":["demo.mod"]}},{"type":"MOD_STATE","variant":"invalid","payload":{"mod_ids":["bad.mod"]}},{"type":"UNKNOWN","variant":"noop","payload":{}}]}',
            assistant=assistant,
        )

        self.assertEqual(parsed["analysis"], "keep-analysis")
        self.assertEqual(len(parsed["actions"]), 1)
        self.assertEqual(parsed["actions"][0]["payload"]["mod_ids"], ["demo.mod"])

    def test_parse_final_text_falls_back_to_plain_text_when_no_json_found(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        parsed = runtime._parse_final_text("plain answer only")

        self.assertEqual(parsed["analysis"], "plain answer only")
        self.assertEqual(parsed["actions"], [])

    def test_extract_streaming_analysis_preview_decodes_partial_json_string(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        preview = runtime._extract_streaming_analysis_preview('{"analysis":"第一行\\n第二行，包含\\"引')

        self.assertEqual(preview, '第一行\n第二行，包含"引')

    def test_stream_completion_emits_only_analysis_text_chunks(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), StreamingJsonLlmStub())
        captured_events = []
        original_emit = assistant_runtime_module.EventBus.emit
        assistant_runtime_module.EventBus.emit = lambda event_name, data=None: captured_events.append((event_name, data))
        try:
            result = runtime._stream_completion(
                messages=[{"role": "user", "content": "hi"}],
                llm_kwargs={"model": "test-model"},
                session_id="session-stream",
                tools=None,
                tool_choice=None,
            )
        finally:
            assistant_runtime_module.EventBus.emit = original_emit

        content_events = [
            payload for event_name, payload in captured_events
            if event_name == "ai-chat-stream" and payload.get("type") == "content"
        ]
        streamed_text = "".join(str(item.get("chunk") or "") for item in content_events)

        self.assertEqual(streamed_text, '第一行\n第二行，包含"引号"')
        self.assertIn('"actions"', result["final_text"])

    def test_run_completion_disables_tools_when_provider_rejects_tool_calling(self):
        llm = ToolUnsupportedThenStreamingLlmStub()
        runtime = AssistantRuntime(AIDefinitionManagerStub(), llm)
        tools = [{"type": "function", "function": {"name": "lookup", "description": "lookup", "parameters": {}}}]

        result = runtime._run_completion_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            llm_kwargs={"model": "ollama_chat/gpt-oss-20b:latest"},
            session_id="session-tool-fallback",
            tools=tools,
            tool_choice="auto",
        )

        self.assertEqual(result["final_text"], '{"analysis":"fallback"}')
        self.assertEqual(llm.completion_calls, 2)
        self.assertIsNotNone(llm.calls[0]["tools"])
        self.assertIsNone(llm.calls[1]["tools"])
        self.assertIsNone(llm.calls[1]["tool_choice"])
        self.assertEqual(llm.calls[1]["messages"][-1]["role"], "user")
        self.assertIn("不支持原生工具调用", llm.calls[1]["messages"][0]["content"])
        self.assertEqual(result["warnings"][0]["code"], "tools_unsupported")
        self.assertIn("不支持工具调用", result["warnings"][0]["message"])

    def test_run_session_returns_warning_when_provider_rejects_tool_calling(self):
        llm = ToolUnsupportedThenStreamingLlmStub()
        runtime = AssistantRuntime(AIDefinitionManagerStub(), llm)
        runtime.definition_manager.assistants["assistant.demo"]["tool_scope_selectable"] = ["lookup"]

        result = runtime.run_session(
            {
                "session_id": "session-tool-warning",
                "assistant_id": "assistant.demo",
                "question": "hi",
                "enabled_tools": ["lookup"],
                "attachments": [],
            },
            active_context=None,
            reader=None,
        )

        self.assertEqual(result["analysis"], "fallback")
        self.assertEqual(result["warnings"][0]["code"], "tools_unsupported")
        self.assertIn("不支持工具调用", result["warnings"][0]["message"])

    def test_runtime_emits_initial_request_usage_event(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())
        captured_events = []
        original_emit = assistant_runtime_module.EventBus.emit
        assistant_runtime_module.EventBus.emit = lambda event_name, data=None: captured_events.append((event_name, data))
        try:
            runtime.run_session(
                {
                    "session_id": "session-usage-event",
                    "assistant_context": {
                        "assistant_id": "assistant.demo",
                        "owner_type": "assistant",
                        "owner_key": "demo",
                        "request_payload": {
                            "client_request_id": "req-1",
                            "question": "hi",
                            "attachments": [],
                            "enabled_tools": [],
                            "ai_override_config": {},
                        },
                    },
                },
                active_context=None,
                reader=None,
            )
        finally:
            assistant_runtime_module.EventBus.emit = original_emit

        usage_events = [payload for event_name, payload in captured_events if event_name == "ai-request-usage"]
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0]["request_id"], "req-1")
        self.assertGreater(usage_events[0]["token_usage"]["estimated_prompt_tokens"], 0)
        self.assertGreater(usage_events[0]["message_usage"]["user"]["total_tokens"], 0)
        self.assertGreaterEqual(usage_events[0]["prompt_input_breakdown"]["total_tokens"], 0)

    def test_estimate_session_request_reuses_runtime_prompt_building(self):
        runtime = AssistantRuntime(AIDefinitionManagerStub(), LlmStub())

        estimate = runtime.estimate_session_request(
            {
                "session_id": "session-estimate",
                "assistant_id": "assistant.demo",
                "question": "hi",
                "history": [],
                "attachments": [],
            },
            active_context=None,
            reader=None,
        )

        self.assertEqual(estimate["assistant_id"], "assistant.demo")
        self.assertEqual(estimate["question"], "hi")
        self.assertGreater(estimate["token_usage"]["estimated_prompt_tokens"], 0)
        self.assertEqual(
            estimate["message_usage"]["user"]["total_tokens"],
            estimate["token_usage"]["estimated_prompt_tokens"],
        )
        self.assertGreaterEqual(estimate["prompt_input_breakdown"]["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
