import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


fake_tools_module = types.ModuleType("backend.ai.tools")
fake_tools_module.AIToolExecutor = type("AIToolExecutor", (), {})
sys.modules["backend.ai.tools"] = fake_tools_module

fake_prompts_module = types.ModuleType("backend.ai.prompts")


class DummyPromptManager:
    def __init__(self, prompt_file: str):
        self.prompt_file = prompt_file
        self.prompts = {}

    def save_prompt(self, prompt_id: str, prompt_data: dict):
        self.prompts[prompt_id] = prompt_data
        return self.prompts

    def delete_prompt(self, prompt_id: str):
        self.prompts.pop(prompt_id, None)
        return self.prompts

    def reset_system_prompts(self):
        return self.prompts


fake_prompts_module.PromptManager = DummyPromptManager
sys.modules["backend.ai.prompts"] = fake_prompts_module

fake_llm_gateway_module = types.ModuleType("backend.ai.llm_gateway")
fake_llm_gateway_module.LiteLLMGateway = type("LiteLLMGateway", (), {})
sys.modules["backend.ai.llm_gateway"] = fake_llm_gateway_module

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

AIManager = importlib.import_module("backend.ai.service").AIManager


class TestAIServiceHelpers(unittest.TestCase):
    def test_summarize_log_context_uses_current_payload_shape(self):
        manager = AIManager.__new__(AIManager)

        summary = manager._summarize_tool_result(
            "get_log_context",
            json.dumps(
                {
                    "representative_line": 128,
                    "total_repeats": 3,
                    "stack_excerpt_lines_provided": 15,
                    "context_content": "sample context",
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(summary, "已返回代表行 #128 的日志上下文")

    def test_summarize_user_data_matches_current_tool_name(self):
        manager = AIManager.__new__(AIManager)

        summary = manager._summarize_tool_result(
            "get_mod_user_data",
            json.dumps(
                {
                    "package_id": "example.mod",
                    "alias_name": "Example",
                    "tags": [],
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(summary, "已返回模组的用户备注/标签/分组信息")


if __name__ == "__main__":
    unittest.main()
