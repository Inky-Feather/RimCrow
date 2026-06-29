import unittest

from backend.ai.ai_gateway import LiteLLMGateway, validate_ai_connection_config
from backend.settings import AIConfig, settings


class TestAIGatewayRequestCompat(unittest.TestCase):
    def setUp(self):
        self.gateway = LiteLLMGateway()

    def _meta(self, model, base_url, endpoint_mode="chat_completions"):
        return {
            "provider": "openai_compatible",
            "base_url": base_url,
            "raw_model": model,
            "endpoint_mode": endpoint_mode,
            "enable_reasoning": True,
            "reasoning_mode": "high",
            "reasoning_effort": "high",
        }

    def _request(self, *, reasoning=True):
        return {
            "api_key": "test-key",
            "model": "unused",
            "temperature": 0.7,
            "max_output_tokens": 5000,
            "_rimcrow_enable_reasoning": reasoning,
            "_rimcrow_reasoning_mode": "high" if reasoning else "off",
            "_rimcrow_reasoning_effort": "high" if reasoning else "auto",
        }

    def test_openai_reasoning_chat_uses_chat_specific_token_and_reasoning_fields(self):
        meta = self._meta("gpt-5", "https://api.openai.com/v1")
        sanitized, _ = self.gateway._sanitize_openai_compatible_params(self._request(), meta)

        kwargs = self.gateway._build_openai_chat_create_kwargs(
            [{"role": "user", "content": "hi"}],
            sanitized,
            meta,
            stream=False,
        )

        self.assertEqual(kwargs["max_completion_tokens"], 5000)
        self.assertNotIn("max_tokens", kwargs)
        self.assertEqual(kwargs["reasoning_effort"], "high")
        self.assertNotIn("reasoning", kwargs)
        self.assertNotIn("temperature", kwargs)

    def test_openai_reasoning_auto_omits_explicit_reasoning_effort(self):
        meta = self._meta("gpt-5", "https://api.openai.com/v1")
        request = self._request()
        request["_rimcrow_reasoning_mode"] = "auto"
        request["_rimcrow_reasoning_effort"] = "auto"
        sanitized, _ = self.gateway._sanitize_openai_compatible_params(request, meta)

        kwargs = self.gateway._build_openai_chat_create_kwargs(
            [{"role": "user", "content": "hi"}],
            sanitized,
            meta,
            stream=False,
        )

        self.assertEqual(kwargs["max_completion_tokens"], 5000)
        self.assertNotIn("reasoning_effort", kwargs)

    def test_openai_reasoning_responses_uses_responses_fields(self):
        meta = self._meta("o3", "https://api.openai.com/v1", endpoint_mode="responses")
        sanitized, _ = self.gateway._sanitize_openai_compatible_params(self._request(), meta)

        kwargs = self.gateway._build_openai_responses_create_kwargs(
            [{"role": "user", "content": "hi"}],
            sanitized,
            meta,
        )

        self.assertEqual(kwargs["max_output_tokens"], 5000)
        self.assertEqual(kwargs["reasoning"], {"effort": "high"})
        self.assertNotIn("temperature", kwargs)

    def test_litellm_request_maps_internal_output_budget_to_wire_max_tokens(self):
        kwargs = self.gateway._normalize_litellm_request_fields({
            "model": "anthropic/claude-sonnet-4",
            "max_output_tokens": 6000,
            "_rimcrow_provider": "anthropic",
        })

        self.assertEqual(kwargs["max_tokens"], 6000)
        self.assertNotIn("max_output_tokens", kwargs)
        self.assertNotIn("_rimcrow_provider", kwargs)

    def test_request_log_redaction_preserves_token_budget_fields(self):
        redacted = self.gateway._redact_request_kwargs_for_log({
            "api_key": "sk-1234567890abcdef",
            "max_output_tokens": 64,
            "access_token": "secret-token-value",
        })

        self.assertEqual(redacted["api_key"], "sk-1...cdef")
        self.assertEqual(redacted["max_output_tokens"], 64)
        self.assertNotEqual(redacted["access_token"], "secret-token-value")

    def test_model_cache_key_does_not_contain_plain_api_key(self):
        secret = "sk-plain-cache-secret"
        self.gateway._fetch_models = lambda provider, base_url, api_key: ["model-a"]

        self.gateway.get_models({
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": secret,
        })

        self.assertTrue(self.gateway._model_cache)
        self.assertFalse(any(secret in cache_key for cache_key in self.gateway._model_cache))

    def test_ollama_connection_config_allows_empty_base_url(self):
        cfg = AIConfig(
            enabled=True,
            provider="ollama",
            model="qwen3:14b",
            base_url="",
            api_key="",
        )

        ok, message = validate_ai_connection_config(cfg)

        self.assertTrue(ok)
        self.assertEqual(message, "")

    def test_official_openai_default_base_requires_api_key(self):
        cfg = AIConfig(
            enabled=True,
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="",
            api_key="",
        )

        ok, message = validate_ai_connection_config(cfg)

        self.assertFalse(ok)
        self.assertEqual(message, "当前协议要求填写 API Key。")

    def test_build_kwargs_ollama_empty_base_url_uses_chat_endpoint_and_default_api_base(self):
        previous_ai = settings.config.ai
        settings.config.ai = AIConfig(
            enabled=True,
            provider="ollama",
            model="qwen3:14b",
            base_url="",
            api_key="",
            max_output_tokens=0,
        )
        try:
            kwargs = self.gateway.build_kwargs()
        finally:
            settings.config.ai = previous_ai

        self.assertEqual(kwargs["model"], "ollama_chat/qwen3:14b")
        self.assertEqual(kwargs["api_base"], "http://127.0.0.1:11434")

    def test_openai_compatible_lm_studio_root_base_url_is_normalized_to_v1(self):
        previous_ai = settings.config.ai
        settings.config.ai = AIConfig(
            enabled=True,
            provider="openai_compatible",
            model="google/gemma-4-e4b",
            base_url="http://127.0.0.1:1234",
            api_key="test-key",
            max_output_tokens=64,
        )
        try:
            llm_kwargs = self.gateway.build_kwargs()
        finally:
            settings.config.ai = previous_ai

        self.assertEqual(llm_kwargs["api_base"], "http://127.0.0.1:1234/v1")

    def test_openai_compatible_existing_v1_base_url_is_preserved(self):
        previous_ai = settings.config.ai
        settings.config.ai = AIConfig(
            enabled=True,
            provider="openai_compatible",
            model="gpt-5",
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            max_output_tokens=64,
        )
        try:
            llm_kwargs = self.gateway.build_kwargs()
        finally:
            settings.config.ai = previous_ai

        self.assertEqual(llm_kwargs["api_base"], "https://api.openai.com/v1")

    def test_openai_compatible_model_is_prefixed_for_routing_but_raw_on_wire(self):
        previous_ai = settings.config.ai
        settings.config.ai = AIConfig(
            enabled=True,
            provider="openai_compatible",
            model="google/gemma-4-e4b",
            base_url="http://127.0.0.1:1234",
            api_key="test-key",
            max_output_tokens=64,
        )
        try:
            llm_kwargs = self.gateway.build_kwargs()
            request_kwargs, meta = self.gateway._strip_private_meta(llm_kwargs)
            sanitized, _ = self.gateway._sanitize_openai_compatible_params(request_kwargs, meta)
            create_kwargs = self.gateway._build_openai_chat_create_kwargs(
                [{"role": "user", "content": "hi"}],
                sanitized,
                meta,
                stream=False,
            )
        finally:
            settings.config.ai = previous_ai

        self.assertEqual(llm_kwargs["model"], "openai/google/gemma-4-e4b")
        self.assertEqual(request_kwargs["model"], "openai/google/gemma-4-e4b")
        self.assertEqual(meta["raw_model"], "google/gemma-4-e4b")
        self.assertEqual(create_kwargs["model"], "google/gemma-4-e4b")
        self.assertEqual(llm_kwargs["api_base"], "http://127.0.0.1:1234/v1")

    def test_openai_compatible_existing_openai_prefix_is_not_duplicated(self):
        request_kwargs, meta = self.gateway._strip_private_meta({
            "_rimcrow_provider": "openai_compatible",
            "_rimcrow_raw_model": "openai/google/gemma-4-e4b",
            "model": "openai/google/gemma-4-e4b",
        })

        self.assertEqual(request_kwargs["model"], "openai/google/gemma-4-e4b")
        self.assertEqual(meta["raw_model"], "google/gemma-4-e4b")

    def test_deepseek_reasoner_does_not_replay_reasoning_or_send_vendor_thinking(self):
        meta = self._meta("deepseek-reasoner", "https://api.deepseek.com")
        request = self._request(reasoning=False)
        messages = [
            {"role": "assistant", "content": "answer", "reasoning_content": "hidden"},
            {"role": "user", "content": "next"},
        ]

        kwargs = self.gateway._build_openai_chat_create_kwargs(messages, request, meta, stream=False)

        self.assertNotIn("reasoning_content", kwargs["messages"][0])
        self.assertNotIn("extra_body", kwargs)

    def test_deepseek_v4_thinking_uses_controls_and_replays_reasoning_for_tools(self):
        meta = self._meta("deepseek-v4-pro", "https://api.deepseek.com")
        messages = [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "trace",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "{}"},
        ]

        kwargs = self.gateway._build_openai_chat_create_kwargs(messages, self._request(), meta, stream=False)

        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled"}})
        self.assertEqual(kwargs["reasoning_effort"], "high")
        self.assertEqual(kwargs["messages"][0]["reasoning_content"], "trace")

    def test_deepseek_v4_auto_keeps_thinking_control_without_forcing_effort(self):
        meta = self._meta("deepseek-v4-pro", "https://api.deepseek.com")
        request = self._request()
        request["_rimcrow_reasoning_mode"] = "auto"
        request["_rimcrow_reasoning_effort"] = "auto"

        kwargs = self.gateway._build_openai_chat_create_kwargs(
            [{"role": "user", "content": "hi"}],
            request,
            meta,
            stream=False,
        )

        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled"}})
        self.assertNotIn("reasoning_effort", kwargs)

    def test_dashscope_qwen_uses_enable_thinking(self):
        meta = self._meta("qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1")

        kwargs = self.gateway._build_openai_chat_create_kwargs(
            [{"role": "user", "content": "hi"}],
            self._request(),
            meta,
            stream=True,
        )

        self.assertEqual(kwargs["extra_body"], {"enable_thinking": True})

    def test_dashscope_qwen36_preserved_thinking_uses_preserve_thinking(self):
        meta = self._meta("qwen3.6-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        messages = [
            {"role": "assistant", "content": "answer", "reasoning_content": "trace"},
            {"role": "user", "content": "next"},
        ]

        kwargs = self.gateway._build_openai_chat_create_kwargs(messages, self._request(), meta, stream=False)

        self.assertEqual(kwargs["extra_body"], {"enable_thinking": True, "preserve_thinking": True})
        self.assertEqual(kwargs["messages"][0]["reasoning_content"], "trace")

    def test_local_qwen_does_not_receive_dashscope_enable_thinking(self):
        meta = self._meta("qwen3:14b", "http://127.0.0.1:11434/v1")

        kwargs = self.gateway._build_openai_chat_create_kwargs(
            [{"role": "user", "content": "hi"}],
            self._request(reasoning=False),
            meta,
            stream=False,
        )

        self.assertNotIn("extra_body", kwargs)

    def test_kimi_preserved_thinking_uses_keep_all_when_reasoning_is_replayed(self):
        meta = self._meta("kimi-k2.6", "https://api.moonshot.cn/v1")
        messages = [
            {"role": "assistant", "content": "answer", "reasoning_content": "trace"},
            {"role": "user", "content": "next"},
        ]

        kwargs = self.gateway._build_openai_chat_create_kwargs(messages, self._request(), meta, stream=True)

        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled", "keep": "all"}})
        self.assertEqual(kwargs["messages"][0]["reasoning_content"], "trace")

    def test_zai_glm_preserved_thinking_uses_clear_thinking_false(self):
        meta = self._meta("glm-4.7", "https://api.z.ai/api/paas/v4")
        messages = [
            {"role": "assistant", "content": "answer", "reasoning_content": "trace"},
            {"role": "user", "content": "next"},
        ]

        kwargs = self.gateway._build_openai_chat_create_kwargs(messages, self._request(), meta, stream=True)

        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled", "clear_thinking": False}})
        self.assertEqual(kwargs["messages"][0]["reasoning_content"], "trace")

    def test_ai_config_auto_token_budget_uses_cloud_model_profile(self):
        cfg = AIConfig(
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )

        self.assertEqual(cfg.resolved_context_window_tokens(), 1000000)
        self.assertEqual(cfg.resolved_max_output_tokens(), 64000)
        self.assertEqual(cfg.resolved_max_input_tokens(), 935488)

    def test_ai_config_openai_profile_distinguishes_latest_context_windows(self):
        gpt54 = AIConfig(
            model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )
        gpt52 = AIConfig(
            model="gpt-5.2",
            base_url="https://api.openai.com/v1",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )
        gpt41 = AIConfig(
            model="gpt-4.1",
            base_url="https://api.openai.com/v1",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )

        self.assertEqual(gpt54.resolved_context_window_tokens(), 1050000)
        self.assertEqual(gpt54.resolved_max_output_tokens(), 128000)
        self.assertEqual(gpt52.resolved_context_window_tokens(), 400000)
        self.assertEqual(gpt52.resolved_max_output_tokens(), 128000)
        self.assertEqual(gpt41.resolved_context_window_tokens(), 1047576)
        self.assertEqual(gpt41.resolved_max_output_tokens(), 32768)

    def test_ai_config_china_latest_profiles_use_updated_context_windows(self):
        deepseek = AIConfig(
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )
        kimi = AIConfig(
            model="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )
        glm = AIConfig(
            model="glm-5.1",
            base_url="https://api.z.ai/api/paas/v4",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )

        self.assertEqual(deepseek.resolved_context_window_tokens(), 1000000)
        self.assertEqual(deepseek.resolved_max_output_tokens(), 384000)
        self.assertEqual(kimi.resolved_context_window_tokens(), 256000)
        self.assertEqual(kimi.resolved_max_output_tokens(), 96000)
        self.assertEqual(glm.resolved_context_window_tokens(), 198000)
        self.assertEqual(glm.resolved_max_output_tokens(), 128000)

    def test_ai_config_deepseek_legacy_model_ids_keep_smaller_profile(self):
        cfg = AIConfig(
            model="deepseek-v3.2",
            base_url="https://api.deepseek.com",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )

        self.assertEqual(cfg.resolved_context_window_tokens(), 128000)
        self.assertEqual(cfg.resolved_max_output_tokens(), 64000)

    def test_ai_config_local_base_uses_conservative_token_profile(self):
        cfg = AIConfig(
            model="qwen3:14b",
            base_url="http://127.0.0.1:11434/v1",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )

        self.assertEqual(cfg.resolved_context_window_tokens(), 32768)
        self.assertEqual(cfg.resolved_max_output_tokens(), 4096)
        self.assertEqual(cfg.resolved_max_input_tokens(), 28160)

    def test_ai_config_ollama_provider_uses_local_token_profile_without_base_url(self):
        cfg = AIConfig(
            provider="ollama",
            model="qwen3:14b",
            base_url="",
            max_output_tokens=0,
            max_input_tokens=0,
            context_window_tokens=0,
        )

        self.assertEqual(cfg.resolved_context_window_tokens(), 32768)
        self.assertEqual(cfg.resolved_max_output_tokens(), 4096)

    def test_ai_config_explicit_token_budget_overrides_model_profile(self):
        cfg = AIConfig(
            model="gpt-5",
            base_url="https://api.openai.com/v1",
            max_output_tokens=3000,
            max_input_tokens=7000,
            context_window_tokens=16000,
        )

        self.assertEqual(cfg.resolved_context_window_tokens(), 16000)
        self.assertEqual(cfg.resolved_max_output_tokens(), 3000)
        self.assertEqual(cfg.resolved_max_input_tokens(), 7000)


if __name__ == "__main__":
    unittest.main()

