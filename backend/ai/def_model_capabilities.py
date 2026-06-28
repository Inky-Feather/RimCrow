"""Model capability policy definitions for the AI gateway."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


GPT5_MODEL_RE = re.compile(r"^gpt-5(?:$|[-.].*)", re.IGNORECASE)
OPENAI_O_SERIES_MODEL_RE = re.compile(r"^o(?:1|3|4)(?:$|[-.].*)", re.IGNORECASE)
OPENAI_REASONING_MODEL_RE = re.compile(r"^(?:gpt-5|o(?:1|3|4))(?:$|[-.].*)", re.IGNORECASE)
DEEPSEEK_THINKING_CONTROL_MODEL_RE = re.compile(r"^deepseek-v(?:3\.2|4)(?:$|[-.].*)", re.IGNORECASE)
DASHSCOPE_PRESERVE_THINKING_MODEL_RE = re.compile(r"^qwen3\.6(?:$|[-.].*)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ModelCapabilityPolicy:
    """模型兼容策略。

    这里只表达网关真实消费的模型能力差异，避免 provider/model 特判散落在请求路由代码里。
    """

    name: str
    matches: tuple[re.Pattern[str], ...]
    supports_reasoning: bool = False
    requires_reasoning_replay: bool = False
    prefer_responses: bool = False
    reasoning_extra_body: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ModelTokenBudgetPolicy:
    """模型 Token 预算预设。

    context_window_tokens 表达模型输入+输出总窗口。
    default_output_tokens 表达用户未显式配置时的后端输出保护阀。
    """

    name: str
    matches: tuple[re.Pattern[str], ...]
    context_window_tokens: int
    default_output_tokens: int


DEFAULT_CONTEXT_WINDOW_TOKENS = 32_768
DEFAULT_OUTPUT_TOKENS = 4_096
DEFAULT_INPUT_TOKENS = 12_000
LOCAL_CONTEXT_WINDOW_TOKENS = 32_768
LOCAL_OUTPUT_TOKENS = 4_096


MODEL_TOKEN_BUDGET_POLICIES: tuple[ModelTokenBudgetPolicy, ...] = (
    ModelTokenBudgetPolicy(
        name="openai-gpt55-gpt54",
        matches=(re.compile(r"^gpt-5\.(?:4|5)(?:$|[-.].*)", re.IGNORECASE),),
        context_window_tokens=1_050_000,
        default_output_tokens=128_000,
    ),
    ModelTokenBudgetPolicy(
        name="openai-gpt5-modern",
        matches=(re.compile(r"^gpt-5(?:\.(?:1|2|3))?(?:$|[-.].*)", re.IGNORECASE),),
        context_window_tokens=400_000,
        default_output_tokens=128_000,
    ),
    ModelTokenBudgetPolicy(
        name="openai-gpt41",
        matches=(re.compile(r"^gpt-4\.1(?:$|[-.].*)", re.IGNORECASE),),
        context_window_tokens=1_047_576,
        default_output_tokens=32_768,
    ),
    ModelTokenBudgetPolicy(
        name="openai-o-series",
        matches=(OPENAI_O_SERIES_MODEL_RE,),
        context_window_tokens=200_000,
        default_output_tokens=100_000,
    ),
    ModelTokenBudgetPolicy(
        name="openai-reasoning",
        matches=(OPENAI_REASONING_MODEL_RE,),
        context_window_tokens=128_000,
        default_output_tokens=8_192,
    ),
    ModelTokenBudgetPolicy(
        name="openai-gpt4o",
        matches=(re.compile(r"^gpt-4o(?:$|[-.].*)", re.IGNORECASE),),
        context_window_tokens=128_000,
        default_output_tokens=16_384,
    ),
    ModelTokenBudgetPolicy(
        name="openai-gpt4-turbo",
        matches=(
            re.compile(r"^gpt-4[-.]turbo(?:$|[-.].*)", re.IGNORECASE),
            re.compile(r"^chatgpt-4o", re.IGNORECASE),
        ),
        context_window_tokens=128_000,
        default_output_tokens=4_096,
    ),
    ModelTokenBudgetPolicy(
        name="openai-gpt35",
        matches=(re.compile(r"^gpt-3\.5", re.IGNORECASE),),
        context_window_tokens=16_384,
        default_output_tokens=2_048,
    ),
    ModelTokenBudgetPolicy(
        name="deepseek-v4",
        matches=(re.compile(r"deepseek[-_.]?(?:v4|chat|reasoner)", re.IGNORECASE),),
        context_window_tokens=1_000_000,
        default_output_tokens=384_000,
    ),
    ModelTokenBudgetPolicy(
        name="deepseek-v3-r1",
        matches=(re.compile(r"deepseek[-_.]?(?:v3(?:\.?[12])?|r1)", re.IGNORECASE),),
        context_window_tokens=128_000,
        default_output_tokens=64_000,
    ),
    ModelTokenBudgetPolicy(
        name="deepseek",
        matches=(re.compile(r"deepseek", re.IGNORECASE),),
        context_window_tokens=1_000_000,
        default_output_tokens=384_000,
    ),
    ModelTokenBudgetPolicy(
        name="qwen-long",
        matches=(re.compile(r"qwen[-_.]?long", re.IGNORECASE),),
        context_window_tokens=10_000_000,
        default_output_tokens=64_000,
    ),
    ModelTokenBudgetPolicy(
        name="qwen-1m",
        matches=(
            re.compile(r"qwen3\.6[-_.]?(?:plus|flash)", re.IGNORECASE),
            re.compile(r"qwen3\.5[-_.]?(?:plus|flash)", re.IGNORECASE),
            re.compile(r"qwen[-_.]?(?:plus|flash|turbo)(?:$|[-_.].*)", re.IGNORECASE),
            re.compile(r"qwen3[-_.]?coder[-_.]?(?:plus|flash)", re.IGNORECASE),
            re.compile(r"qwen2\.5[-_.]?(?:72b|32b|14b|7b).*instruct", re.IGNORECASE),
        ),
        context_window_tokens=1_000_000,
        default_output_tokens=64_000,
    ),
    ModelTokenBudgetPolicy(
        name="qwen3-max",
        matches=(re.compile(r"qwen3\.6[-_.]?max|qwen3[-_.]?max", re.IGNORECASE),),
        context_window_tokens=256_000,
        default_output_tokens=64_000,
    ),
    ModelTokenBudgetPolicy(
        name="qwen-max",
        matches=(re.compile(r"qwen[-_.]?max", re.IGNORECASE),),
        context_window_tokens=128_000,
        default_output_tokens=32_000,
    ),
    ModelTokenBudgetPolicy(
        name="qwen3-family",
        matches=(re.compile(r"qwen3(?:\.5)?", re.IGNORECASE),),
        context_window_tokens=256_000,
        default_output_tokens=64_000,
    ),
    ModelTokenBudgetPolicy(
        name="qwen",
        matches=(
            re.compile(r"qwq", re.IGNORECASE),
            re.compile(r"qwen", re.IGNORECASE),
        ),
        context_window_tokens=128_000,
        default_output_tokens=8_192,
    ),
    ModelTokenBudgetPolicy(
        name="kimi-k2",
        matches=(
            re.compile(r"kimi[-_.]?k2(?:\.|[-_.])?(?:6|5|thinking|turbo|0905)", re.IGNORECASE),
            re.compile(r"moonshot[-_.]?kimi[-_.]?k2", re.IGNORECASE),
        ),
        context_window_tokens=256_000,
        default_output_tokens=96_000,
    ),
    ModelTokenBudgetPolicy(
        name="kimi",
        matches=(
            re.compile(r"kimi", re.IGNORECASE),
            re.compile(r"moonshot", re.IGNORECASE),
        ),
        context_window_tokens=128_000,
        default_output_tokens=8_192,
    ),
    ModelTokenBudgetPolicy(
        name="glm-latest",
        matches=(re.compile(r"glm[-_.]?(?:5(?:\.1)?|4\.[5-9])", re.IGNORECASE),),
        context_window_tokens=198_000,
        default_output_tokens=128_000,
    ),
    ModelTokenBudgetPolicy(
        name="glm",
        matches=(
            re.compile(r"glm", re.IGNORECASE),
            re.compile(r"zhipu", re.IGNORECASE),
        ),
        context_window_tokens=128_000,
        default_output_tokens=8_192,
    ),
    ModelTokenBudgetPolicy(
        name="doubao",
        matches=(re.compile(r"doubao", re.IGNORECASE),),
        context_window_tokens=256_000,
        default_output_tokens=32_000,
    ),
    ModelTokenBudgetPolicy(
        name="minimax",
        matches=(re.compile(r"minimax", re.IGNORECASE),),
        context_window_tokens=192_000,
        default_output_tokens=32_000,
    ),
    ModelTokenBudgetPolicy(
        name="claude-modern",
        matches=(re.compile(r"claude[-_.]?(?:sonnet[-_.]?4|3[-_.]?7[-_.]?sonnet)", re.IGNORECASE),),
        context_window_tokens=200_000,
        default_output_tokens=64_000,
    ),
    ModelTokenBudgetPolicy(
        name="claude-opus",
        matches=(re.compile(r"claude[-_.]?opus[-_.]?4(?:[-_.]?1)?", re.IGNORECASE),),
        context_window_tokens=200_000,
        default_output_tokens=32_000,
    ),
    ModelTokenBudgetPolicy(
        name="claude",
        matches=(re.compile(r"claude", re.IGNORECASE),),
        context_window_tokens=200_000,
        default_output_tokens=8_192,
    ),
    ModelTokenBudgetPolicy(
        name="gemini",
        matches=(re.compile(r"gemini", re.IGNORECASE),),
        context_window_tokens=1_048_576,
        default_output_tokens=65_536,
    ),
    ModelTokenBudgetPolicy(
        name="mistral",
        matches=(re.compile(r"mistral", re.IGNORECASE),),
        context_window_tokens=128_000,
        default_output_tokens=8_192,
    ),
    ModelTokenBudgetPolicy(
        name="local-common",
        matches=(
            re.compile(r"llama", re.IGNORECASE),
            re.compile(r"mixtral", re.IGNORECASE),
            re.compile(r"yi[-_.]?", re.IGNORECASE),
        ),
        context_window_tokens=LOCAL_CONTEXT_WINDOW_TOKENS,
        default_output_tokens=LOCAL_OUTPUT_TOKENS,
    ),
)


def is_local_openai_compatible_base(base_url: str) -> bool:
    """判断 OpenAI-compatible base_url 是否为本地服务。"""
    try:
        host = (urlparse(str(base_url or "")).hostname or "").lower()
    except Exception:
        host = ""
    return host in {"127.0.0.1", "localhost", "0.0.0.0"} or host.endswith(".local")


def resolve_model_token_budget(model: str, base_url: str = "") -> dict[str, Any]:
    """按模型名/端点解析默认 token 预算。

    本地端点优先走保守预算，因为 Ollama/vLLM/llama.cpp 的实际上下文窗口常由
    服务端启动参数决定，不能只凭模型名推断。
    """
    normalized_model = str(model or "").strip()
    if is_local_openai_compatible_base(base_url):
        return {
            "name": "local-openai-compatible",
            "context_window_tokens": LOCAL_CONTEXT_WINDOW_TOKENS,
            "default_output_tokens": LOCAL_OUTPUT_TOKENS,
        }

    for policy in MODEL_TOKEN_BUDGET_POLICIES:
        if any(pattern.search(normalized_model) for pattern in policy.matches):
            return {
                "name": policy.name,
                "context_window_tokens": policy.context_window_tokens,
                "default_output_tokens": policy.default_output_tokens,
            }

    return {
        "name": "default",
        "context_window_tokens": DEFAULT_CONTEXT_WINDOW_TOKENS,
        "default_output_tokens": DEFAULT_OUTPUT_TOKENS,
    }


def normalize_reasoning_effort(value: Any) -> str:
    """把前端/配置里的强度值规整为统一逻辑枚举。"""
    normalized = str(value or "").strip().lower()
    if normalized in ("", "default"): return "auto"
    alias_map = {
        "auto": "auto",
        "minimal": "low",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "max": "xhigh",
    }
    return alias_map.get(normalized, "auto")


def normalize_reasoning_mode(value: Any) -> str:
    """把会话级思考模式规整成统一枚举。"""
    normalized = str(value or "").strip().lower()
    alias_map = {
        "": "auto",
        "off": "off",
        "disable": "off",
        "disabled": "off",
        "false": "off",
        "0": "off",
        "auto": "auto",
        "on": "auto",
        "enable": "auto",
        "enabled": "auto",
        "true": "auto",
        "1": "auto",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "max": "xhigh",
    }
    return alias_map.get(normalized, "auto")


MODEL_CAPABILITY_POLICIES: tuple[ModelCapabilityPolicy, ...] = (
    ModelCapabilityPolicy(
        name="openai-reasoning",
        matches=(OPENAI_REASONING_MODEL_RE,),
        supports_reasoning=True,
        prefer_responses=True,
        reasoning_extra_body={"reasoning": {"effort": "medium"}},
    ),
    ModelCapabilityPolicy(
        name="deepseek-thinking",
        matches=(re.compile(r"deepseek", re.IGNORECASE),),
        supports_reasoning=True,
        reasoning_extra_body={"thinking": {"type": "enabled"}},
    ),
    ModelCapabilityPolicy(
        name="qwen-thinking",
        matches=(
            re.compile(r"qwq", re.IGNORECASE),
            re.compile(r"qwen3", re.IGNORECASE),
            re.compile(r"qwen[-_.]?(max|plus)", re.IGNORECASE),
        ),
        supports_reasoning=True,
        reasoning_extra_body={"enable_thinking": True},
    ),
    ModelCapabilityPolicy(
        name="kimi-thinking",
        matches=(
            re.compile(r"kimi", re.IGNORECASE),
            re.compile(r"moonshot", re.IGNORECASE),
        ),
        supports_reasoning=True,
        requires_reasoning_replay=True,
        reasoning_extra_body={"thinking": {"type": "enabled"}},
    ),
    ModelCapabilityPolicy(
        name="doubao-thinking",
        matches=(re.compile(r"doubao", re.IGNORECASE),),
        supports_reasoning=True,
        reasoning_extra_body={"thinking": {"type": "enabled"}},
    ),
    ModelCapabilityPolicy(
        name="glm-thinking",
        matches=(
            re.compile(r"glm-4\.5", re.IGNORECASE),
            re.compile(r"glm", re.IGNORECASE),
        ),
        supports_reasoning=True,
        requires_reasoning_replay=True,
        reasoning_extra_body={"thinking": {"type": "enabled"}},
    ),
)
