import unittest

from backend.ai.attachment_resolver import AttachmentResolver


class AIDefinitionManagerStub:
    def __init__(self):
        self.attachment_definitions = {}

    def get_attachment_projection_fields(self, kind, prompt_id=None, options=None):
        return []


class LlmStub:
    def estimate_text_tokens(self, text, model_name):
        return len(text)


class TestAttachmentResolver(unittest.TestCase):
    def test_extract_prompt_variables_uses_diagnosis_context_source_fields(self):
        resolver = AttachmentResolver(AIDefinitionManagerStub(), LlmStub())
        attachment = type("AttachmentStub", (), {})()
        attachment.type = "diagnosis_context"
        attachment.title = "已选中日志"
        attachment.summary = "1 条已选日志"
        attachment.facts = {
            "source_type": "game",
            "filename": "RMM_Realtime.log",
            "errors": [{"target_line": 588}],
        }

        variables = resolver.extract_prompt_variables([attachment])

        self.assertEqual(variables["diagnosis_context.source_type"], "game")
        self.assertEqual(variables["diagnosis_context.filename"], "RMM_Realtime.log")


if __name__ == "__main__":
    unittest.main()
