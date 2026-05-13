"""Model capability policy definitions for the AI gateway."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


GPT5_MODEL_RE = re.compile(r"^gpt-5(?:$|[-.].*)", re.IGNORECASE)


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
        name="openai-gpt5",
        matches=(GPT5_MODEL_RE,),
        supports_reasoning=True,
        prefer_responses=True,
        reasoning_extra_body={"reasoning": {"effort": "medium"}},
    ),
    ModelCapabilityPolicy(
        name="deepseek-thinking",
        matches=(re.compile(r"deepseek", re.IGNORECASE),),
        supports_reasoning=True,
        requires_reasoning_replay=True,
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
        requires_reasoning_replay=True,
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
