import importlib
import json
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import TypeAdapter

from backend.ai.ai_contracts import AssistantDefinition, ModAliasGenerationItem

_STUBBED_MODULE_NAMES = [
    "backend.ai.prompts",
    "backend.ai.llm_gateway",
    "backend.ai.ai_gateway",
    "backend.database.dao",
    "json_repair",
    "backend.settings",
    "backend.utils.logger",
    "backend.utils.constants",
    "backend.utils.event_bus",
    "backend.ai.assistant_runtime",
    "backend.ai.ai_service",
]
_ORIGINAL_MODULES = {name: sys.modules.get(name) for name in _STUBBED_MODULE_NAMES}


def _restore_stubbed_modules():
    for name, module in _ORIGINAL_MODULES.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


fake_prompts_module = types.ModuleType("backend.ai.prompts")


class DummyAIDefinitionManager:
    def __init__(self, prompt_file: str):
        self.prompt_file = prompt_file
        self.prompts = {}
        self.attachment_definitions = {}

    def save_prompt(self, prompt_id: str, prompt_data: dict):
        self.prompts[prompt_id] = prompt_data
        return self.prompts

    def delete_prompt(self, prompt_id: str):
        self.prompts.pop(prompt_id, None)
        return self.prompts

    def reset_system_prompts(self):
        return self.prompts


fake_prompts_module.AIDefinitionManager = DummyAIDefinitionManager
sys.modules["backend.ai.prompts"] = fake_prompts_module

fake_llm_gateway_module = types.ModuleType("backend.ai.llm_gateway")
fake_llm_gateway_module.LiteLLMGateway = type("LiteLLMGateway", (), {})
sys.modules["backend.ai.llm_gateway"] = fake_llm_gateway_module
fake_ai_gateway_module = types.ModuleType("backend.ai.ai_gateway")
fake_ai_gateway_module.LiteLLMGateway = type("LiteLLMGateway", (), {})
sys.modules["backend.ai.ai_gateway"] = fake_ai_gateway_module

fake_dao_module = types.ModuleType("backend.database.dao")
fake_dao_module.ModDAO = type("ModDAO", (), {})
fake_dao_module.GroupDAO = type("GroupDAO", (), {})
sys.modules["backend.database.dao"] = fake_dao_module

fake_json_repair_module = types.ModuleType("json_repair")
fake_json_repair_module.repair_json = lambda text, return_objects=False: json.loads(text)
sys.modules["json_repair"] = fake_json_repair_module

fake_settings_module = types.ModuleType("backend.settings")
fake_settings_module.DATA_DIR = Path(".")
fake_settings_module.AIConfig = type("AIConfig", (), {})
fake_settings_module.settings = SimpleNamespace(
    config=SimpleNamespace(
        language="zh",
        ai=SimpleNamespace(model="test-model"),
        network=SimpleNamespace(
            hosts={},
            write_to_system_hosts=False,
            proxy=SimpleNamespace(
                enabled=False,
                host="",
                port="",
                username="",
                password="",
                type="http",
                bypass_list=[],
            ),
        ),
    )
)
sys.modules["backend.settings"] = fake_settings_module

fake_logger_module = types.ModuleType("backend.utils.logger")
fake_logger_module.logger = SimpleNamespace(
    error=lambda *args, **kwargs: None,
    warning=lambda *args, **kwargs: None,
    info=lambda *args, **kwargs: None,
    debug=lambda *args, **kwargs: None,
)
sys.modules["backend.utils.logger"] = fake_logger_module

fake_constants_module = types.ModuleType("backend.utils.constants")
fake_constants_module.get_lang_by_code = lambda code: code
sys.modules["backend.utils.constants"] = fake_constants_module

fake_event_bus_module = types.ModuleType("backend.utils.event_bus")
fake_event_bus_module.EventBus = type(
    "EventBus",
    (),
    {"emit": staticmethod(lambda *args, **kwargs: None)},
)
sys.modules["backend.utils.event_bus"] = fake_event_bus_module

class _SafeFormatDict(dict):
    def __missing__(self, key):
        return ""


def _safe_format_template(template, variables):
    double_brace_pattern = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")
    pattern = re.compile(r"\{([A-Za-z0-9_.]+)\}")

    def replace(match):
        return str((variables or {}).get(match.group(1), ""))

    formatted = double_brace_pattern.sub(replace, str(template or ""))
    return pattern.sub(replace, formatted)

fake_assistant_runtime_module = types.ModuleType("backend.ai.assistant_runtime")
fake_assistant_runtime_module.AssistantRuntime = type("AssistantRuntime", (), {"__init__": lambda self, *args, **kwargs: None})
fake_assistant_runtime_module.build_llm_kwargs = lambda llm, override_config=None: {}
fake_assistant_runtime_module.estimate_text_tokens = lambda llm, text, model_name: len(str(text or ""))
fake_assistant_runtime_module.get_prompt_config = lambda prompts, prompt_id: prompts.get(prompt_id, {})
fake_assistant_runtime_module.normalize_message_text = lambda llm, content: str(content or "")
fake_assistant_runtime_module.safe_format_template = _safe_format_template
sys.modules["backend.ai.assistant_runtime"] = fake_assistant_runtime_module

AIManager = importlib.import_module("backend.ai.ai_service").AIManager
_restore_stubbed_modules()


class TestAIServiceHelpers(unittest.TestCase):
    def test_resolve_mod_alias_generation_input_items_uses_mod_selection_attachment(self):
        manager = object.__new__(AIManager)
        attachment = type("AttachmentStub", (), {})()
        attachment.type = "mod_selection"
        attachment.facts = {
            "mods": [
                {
                    "package_id": "example.mod",
                    "name": "Example Mod",
                    "description": "mod description",
                }
            ],
        }

        result = manager._resolve_mod_alias_generation_input_items([attachment], {})

        self.assertEqual(
            result,
            [{
                "package_id": "example.mod",
                "name": "Example Mod",
                "description": "mod description",
            }],
        )

    def test_normalize_mod_alias_generation_output_filters_duplicates(self):
        manager = object.__new__(AIManager)
        normalized = manager._normalize_mod_alias_generation_output(
            [
                {"package_id": "a.mod", "alias_name": "A", "notes": "1"},
                {"package_id": "a.mod", "alias_name": "A2", "notes": "2"},
                {"package_id": "b.mod", "alias_name": "B", "notes": ""},
                {"package_id": "", "alias_name": "X", "notes": ""},
            ]
        )

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["package_id"], "a.mod")
        self.assertEqual(normalized[1]["package_id"], "b.mod")

    def test_safe_format_missing_variables_become_empty(self):
        manager = object.__new__(AIManager)

        formatted = manager._safe_format("A {missing} B {{present}}", {"present": "X"})

        self.assertEqual(formatted, "A  B X")

    def test_task_output_contract_is_bound_to_task_key(self):
        manager = object.__new__(AIManager)
        manager._structured_output_adapters = {
            "task.mod_alias_generation": TypeAdapter(list[ModAliasGenerationItem]),
        }

        parsed = manager._parse_structured_output(
            "task.mod_alias_generation",
            '[{"package_id":"demo.mod","alias_name":"演示别名","notes":"演示备注"}]',
        )

        self.assertEqual(parsed[0]["package_id"], "demo.mod")
        self.assertEqual(parsed[0]["alias_name"], "演示别名")

    def test_build_task_prompt_config_appends_runtime_output_contract(self):
        manager = object.__new__(AIManager)

        prompt_config = manager._build_task_prompt_config(
            {"system": "你是一个任务助手。", "user_template": "{mod_alias_input_json}"},
            "task.mod_alias_generation",
        )

        self.assertIn("最终输出协议", prompt_config["system"])
        self.assertIn("JSON 数组", prompt_config["system"])
        self.assertTrue(prompt_config["system"].startswith("你是一个任务助手。"))

        translation_prompt = manager._build_task_prompt_config(
            {"system": "你是翻译器。", "user_template": "{translation_input_json}"},
            "task.translation",
        )
        self.assertIn('"segments"', translation_prompt["system"])

    def test_execute_structured_task_uses_task_prompt_context(self):
        manager = object.__new__(AIManager)
        manager._build_task_execution_context = lambda task_key, payload, override_config=None: {
            "prompt_config": {"system": "SYSTEM", "user_template": "{translation_input_json}"},
            "runtime_variables": {"translation_input_json": '{"segments":[]}'},
            "llm_kwargs": {"model": "test-model"},
        }
        manager._build_prompt_messages = lambda prompt_config, variables: [
            {"role": "system", "content": prompt_config["system"]},
            {"role": "user", "content": variables["translation_input_json"]},
        ]
        manager.llm = SimpleNamespace(
            completion=lambda messages, llm_kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"segments":[{"key":"title","text":"译名"}]}'))]
            )
        )
        manager._message_text = lambda content: str(content or "")
        manager._parse_structured_output = lambda task_key, text: json.loads(text)

        parsed = manager.execute_structured_task("task.translation", {"variables": {}})

        self.assertEqual(parsed["segments"][0]["key"], "title")
        self.assertEqual(parsed["segments"][0]["text"], "译名")

    def test_mod_alias_chunk_budget_does_not_treat_output_tokens_as_context_window(self):
        manager = object.__new__(AIManager)
        manager.llm = SimpleNamespace(
            estimate_messages_tokens=lambda messages, model_name: 800,
            _message_text=lambda content: str(content or ""),
        )

        chunk_budget, max_item_tokens = manager._resolve_mod_alias_chunk_token_budget(
            cfg=SimpleNamespace(max_output_tokens=5000),
            model_name="test-model",
            prompt_config={"system": "SYSTEM", "user_template": "{mod_alias_input_json}"},
            runtime_variables={},
        )

        self.assertEqual(chunk_budget, 8944)
        self.assertEqual(max_item_tokens, 8744)

    def test_test_chat_reads_reasoning_field_and_inline_think(self):
        manager = object.__new__(AIManager)
        manager.llm = SimpleNamespace(
            completion=lambda messages, llm_kwargs: SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="<think>local trace</think>ok",
                            reasoning="vllm trace",
                        )
                    )
                ]
            )
        )

        result = manager.test_chat("hi", {})

        self.assertEqual(result["text"], "ok")
        self.assertEqual(result["reasoning_content"], "vllm trace\nlocal trace")
        self.assertEqual(result["raw_message"]["reasoning"], "vllm trace")

    def test_test_chat_reports_empty_choices_response_clearly(self):
        manager = object.__new__(AIManager)
        manager.llm = SimpleNamespace(
            completion=lambda messages, llm_kwargs: SimpleNamespace(
                choices=None,
                error={"message": "bad provider prefix"},
            )
        )

        with self.assertRaises(Exception) as ctx:
            manager.test_chat("hi", {})

        self.assertIn("AI 服务没有返回可用结果", str(ctx.exception))

    def test_assistant_definition_keeps_selectable_tool_scope(self):
        definition = AssistantDefinition.model_validate({
            "id": "assistant.demo",
            "name": "demo",
            "prompt_id": "prompt.demo",
            "tool_scope_selectable": ["search_mods", "get_mod_info"],
        })

        self.assertEqual(definition.tool_scope_selectable, ["search_mods", "get_mod_info"])

    def test_assistant_definition_normalizes_selectable_tool_scope(self):
        definition = AssistantDefinition.model_validate({
            "id": "assistant.demo",
            "name": "demo",
            "prompt_id": "prompt.demo",
            "tool_scope_selectable": ["search_mods", "search_mods", "  "],
        })

        self.assertEqual(definition.tool_scope_selectable, ["search_mods"])


if __name__ == "__main__":
    unittest.main()
