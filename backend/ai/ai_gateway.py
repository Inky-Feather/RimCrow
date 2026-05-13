# backend/ai/llm_gateway.py
"""
统一封装 LiteLLM / OpenAI SDK 的 AI 网关。

职责分为三类：
1. 厂商与模型探测
2. LLM 调用参数组装
3. OpenAI-compatible 协议下的 chat/responses 路由与兼容处理
"""

import asyncio
import inspect
import os
import re
import time
from dataclasses import asdict
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

# 必须在 import litellm 前设置
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LITELLM_LOCAL_ANTHROPIC_BETA_HEADERS"] = "True"
os.environ["LITELLM_LOCAL_BLOG_POSTS"] = "True"

from litellm import completion as litellm_completion, acompletion as litellm_acompletion 
from litellm.utils import token_counter
from openai import OpenAI, AsyncOpenAI

from backend.ai.def_model_capabilities import (
    GPT5_MODEL_RE,
    MODEL_CAPABILITY_POLICIES,
    ModelCapabilityPolicy,
    normalize_reasoning_effort as _normalize_reasoning_effort,
    normalize_reasoning_mode as _normalize_reasoning_mode,
)
from backend.settings import settings
from backend.managers.mgr_network import network_mgr
from backend.utils.logger import logger

DEFAULT_BASE_URLS = {
    "openai_compatible": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "ollama": "http://127.0.0.1:11434",
}

OFFICIAL_OPENAI_HOSTS = {"api.openai.com"}

class LiteLLMGateway:
    """AI 网关。

    外部只需要关心三个公开能力：
    - `get_providers()`
    - `get_models()`
    - `completion()/acompletion()`

    其余方法都属于内部兼容层，用于抹平不同厂商、不同 endpoint 的差异。
    """

    def __init__(self):
        """初始化网关缓存与调试日志开关。"""
        # 如果系统开启了 Debug 模式，开启 LiteLLM 的底层日志，打印完整的请求和响应
        if settings.config.debug_mode:
            os.environ["LITELLM_LOG"] = "DEBUG"
        
        # 轻量级缓存字典，用于缓存自定义接口的模型列表
        # 格式: { "provider_baseurl_apikey": (timestamp, [models...]) }
        self._model_cache: dict[str, tuple[float, list[str]]] = {}
        self._cache_ttl = 300  # 缓存有效期 5 分钟 (300秒)

    # =========================================================================
    # 基础工具
    # =========================================================================
    def _normalize_provider(self, provider: str) -> str:
        """
        兼容老配置：
        - openai -> openai_compatible
        - custom_openai -> openai_compatible
        """
        p = (provider or "").strip().lower()
        if p in ("openai", "custom_openai"):
            return "openai_compatible"
        return p or "openai_compatible"

    def _prepare_proxy_env(self):
        """按当前设置同步 AI 请求所需的代理环境变量。"""
        if not settings.config.network.use_proxy_on_ai:
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                os.environ.pop(key, None)
        else:
            network_mgr.apply_proxy_settings()

    def _requests_proxies(self):
        """为 `requests` 调用生成代理配置；未启用时返回 `None`。"""
        if not settings.config.network.use_proxy_on_ai: return None
        proxy_url = network_mgr.get_proxy_url()
        if not proxy_url: return None
        return {"http": proxy_url, "https": proxy_url}

    def _host(self, base_url: str) -> str:
        """从 Base URL 中提取标准化后的 host。"""
        try:
            return (urlparse(base_url).hostname or "").lower()
        except Exception:
            return ""

    def _is_official_openai_base(self, base_url: str) -> bool:
        """判断当前 Base URL 是否指向 OpenAI 官方域名。"""
        host = self._host(base_url)
        return host in OFFICIAL_OPENAI_HOSTS or host.endswith(".openai.com")

    def _is_gpt5_family(self, model: str) -> bool:
        """判断模型名是否属于 GPT-5 系列。"""
        return bool(GPT5_MODEL_RE.match((model or "").strip()))

    def _resolve_model_capability_policy(self, model: str) -> ModelCapabilityPolicy | None:
        """按模型名解析最先命中的兼容策略。

        这里明确采用“首个命中即生效”的顺序规则：
        - 更具体的规则放前面
        - 更宽泛的家族规则放后面
        """
        normalized_model = (model or "").strip()
        for policy in MODEL_CAPABILITY_POLICIES:
            if any(pattern.search(normalized_model) for pattern in policy.matches):
                return policy
        return None

    def _build_reasoning_mode_meta(self, provider: str, policy: ModelCapabilityPolicy | None) -> dict[str, Any]:
        """把后端内部能力策略规整成前端可直接消费的统一元数据。"""
        supports_reasoning = bool(provider == "openai_compatible" and policy and policy.supports_reasoning)
        supports_reasoning_effort = bool(
            policy and policy.supports_reasoning and (
                policy.name == "openai-gpt5"
                or policy.name == "deepseek-thinking"
            )
        )
        if supports_reasoning_effort:
            reasoning_options = [
                {"value": "off", "label": "关闭"},
                {"value": "auto", "label": "自动"},
                {"value": "low", "label": "低"},
                {"value": "medium", "label": "中"},
                {"value": "high", "label": "高"},
                {"value": "xhigh", "label": "极高"},
            ]
            reasoning_mode_kind = "leveled"
        elif supports_reasoning:
            reasoning_options = [
                {"value": "off", "label": "关闭"},
                {"value": "auto", "label": "自动"},
            ]
            reasoning_mode_kind = "toggle"
        else:
            reasoning_options = [
                {"value": "off", "label": "关闭"},
            ]
            reasoning_mode_kind = "unsupported"

        return {
            "supports_reasoning": supports_reasoning,
            "supports_reasoning_effort": supports_reasoning_effort,
            "reasoning_mode_kind": reasoning_mode_kind,
            "reasoning_options": reasoning_options,
            "default_session_reasoning_mode": "auto" if supports_reasoning else "off",
        }

    def get_model_capabilities(self, config_dict: dict) -> dict[str, Any]:
        """返回当前临时配置对应的模型兼容摘要。

        这里主要给调试或后续诊断接口使用，不再直接暴露给设置页。
        """
        provider = self._normalize_provider(config_dict.get("provider", ""))
        model = str(config_dict.get("model", "") or "").strip()
        base_url = str(config_dict.get("base_url", "") or "").strip()
        policy = self._resolve_model_capability_policy(model)
        reasoning_meta = self._build_reasoning_mode_meta(provider, policy)

        return {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "policy_name": policy.name if policy else "",
            **reasoning_meta,
            "requires_reasoning_replay": bool(policy and policy.requires_reasoning_replay),
            "prefer_responses": bool(policy and policy.prefer_responses),
            "is_official_openai_base": self._is_official_openai_base(base_url) if base_url else False,
        }

    def get_model_capability_meta(self) -> dict[str, Any]:
        """导出前端本地能力判断所需的静态元数据。

        前端会在初始化时拉取一次这份定义，之后只按模型名本地匹配，
        避免模型切换、随机性调整时反复请求后端做同一件事。
        """
        policy_items: list[dict[str, Any]] = []
        for policy in MODEL_CAPABILITY_POLICIES:
            reasoning_meta = self._build_reasoning_mode_meta("openai_compatible", policy)
            policy_items.append({
                "name": policy.name,
                "matches": [pattern.pattern for pattern in policy.matches],
                **reasoning_meta,
                "requires_reasoning_replay": policy.requires_reasoning_replay,
                "prefer_responses": policy.prefer_responses,
            })
        return {
            "provider_scope": "openai_compatible",
            "policies": policy_items,
            "unsupported": self._build_reasoning_mode_meta("unknown", None),
        }

    def _is_retryable_error(self, error: Exception) -> bool:
        """判断是否值得做自动重试。

        优先读取异常上的结构化状态码，其次识别 requests/OpenAI 常见网络异常，
        最后才退回到保守的文本兜底，尽量减少对具体报错文案的脆弱依赖。
        """
        status_candidates = (
            getattr(error, "status_code", None),
            getattr(getattr(error, "response", None), "status_code", None),
            getattr(getattr(error, "response", None), "status", None),
            getattr(getattr(error, "body", None), "status_code", None),
        )
        for raw_status in status_candidates:
            if raw_status is None: continue
            try:
                status_code = int(raw_status)
            except (TypeError, ValueError):
                status_code = None
            if status_code is None: continue
            if status_code in {
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                HTTPStatus.BAD_GATEWAY,
                HTTPStatus.SERVICE_UNAVAILABLE,
                HTTPStatus.GATEWAY_TIMEOUT,
            }:
                return True
            if 500 <= status_code < 600:
                return True

        if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True

        cause = getattr(error, "__cause__", None)
        if isinstance(cause, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True

        text = str(error or "").lower()
        signals = (
            "timeout",
            "timed out",
            "rate limit",
            "connection reset",
            "connection aborted",
            "temporarily unavailable",
            "server error",
        )
        return any(signal in text for signal in signals)

    def _retry_sleep_seconds(self, attempt: int) -> float:
        """统一计算指数退避时长。"""
        return min(1.5 * (2 ** attempt), 5)

    def _call_with_retries_sync(self, func, num_retries: int):
        """同步重试包装器。"""
        last_error = None
        for attempt in range(num_retries + 1):
            try: return func()
            except Exception as e:
                last_error = e
                if attempt >= num_retries or not self._is_retryable_error(e):
                    raise
                sleep_s = self._retry_sleep_seconds(attempt)
                logger.warning(f"[openai_compatible] 请求失败，{sleep_s:.1f}s 后重试: {e}")
                time.sleep(sleep_s)
        raise last_error  # type: ignore

    async def _call_with_retries_async(self, func, num_retries: int):
        """异步重试包装器。"""
        last_error = None
        for attempt in range(num_retries + 1):
            try: return await func()
            except Exception as e:
                last_error = e
                if attempt >= num_retries or not self._is_retryable_error(e):
                    raise
                sleep_s = self._retry_sleep_seconds(attempt)
                logger.warning(f"[openai_compatible] 异步请求失败，{sleep_s:.1f}s 后重试: {e}")
                await asyncio.sleep(sleep_s)
        raise last_error  # type: ignore

    def _log_openai_compatible_notes(self, notes: list[str]) -> None:
        """记录参数兼容修正说明。"""
        for note in notes:
            logger.warning(f"[LLM参数兼容修正] {note}")

    # =========================================================================
    # 厂商与模型探测
    # =========================================================================
    def get_providers(self) -> List[Dict[str, str]]:
        """返回前端设置页使用的协议类型列表。"""
        return [
            {"value": "openai_compatible", "label": "OpenAI 兼容协议（含 OpenAI 官方 / 中转 / 本地服务）"},
            {"value": "anthropic", "label": "Anthropic 原生协议"},
            {"value": "gemini", "label": "Google Gemini 原生协议"},
            {"value": "ollama", "label": "Ollama 原生协议"},
        ]

    # =========================================================================
    # 模型探测
    # =========================================================================
    def get_models(self, config_dict: dict) -> List[str]:
        """根据临时配置拉取模型列表，并对结果做短期缓存。"""
        provider = self._normalize_provider(config_dict.get("provider", ""))
        base_url = (config_dict.get("base_url") or DEFAULT_BASE_URLS.get(provider, "")).rstrip("/")
        api_key = config_dict.get("api_key", "")

        if not provider or not base_url: return []
        cache_key = f"{provider}_{base_url}_{api_key}"
        if cache_key in self._model_cache:
            timestamp, cached_models = self._model_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                return sorted(cached_models, key=lambda x: x.lower())

        models = self._fetch_models(provider, base_url, api_key)
        if models:
            self._model_cache[cache_key] = (time.time(), models)

        return sorted(models, key=lambda x: x.lower())

    def _fetch_models(self, provider: str, base_url: str, api_key: str) -> List[str]:
        """按协议类型探测模型列表。

        这里不走 LiteLLM 的 provider 列表，而是直接请求目标服务，
        这样能兼容中转、自建兼容服务以及本地 Ollama。
        """
        proxies = self._requests_proxies()

        try:
            # 1) Ollama 原生
            if provider == "ollama":
                resp = requests.get(f"{base_url}/api/tags", proxies=proxies, timeout=10)
                if resp.status_code == 200:
                    return [m["name"] for m in resp.json().get("models", []) if m.get("name")]
                return []

            # 2) Gemini 原生
            if provider == "gemini":
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                for endpoint in ("/v1beta/models", "/v1/models"):
                    try:
                        resp = requests.get(
                            f"{base_url}{endpoint}",
                            params={"key": api_key} if api_key else None,
                            headers=headers,
                            proxies=proxies,
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            return [
                                m["name"].replace("models/", "")
                                for m in resp.json().get("models", [])
                                if "generateContent" in (m.get("supportedGenerationMethods") or [])
                            ]
                    except requests.exceptions.RequestException:
                        continue
                return []

            # 3) Anthropic 原生
            if provider == "anthropic":
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                } if api_key else {
                    "anthropic-version": "2023-06-01",
                }
                resp = requests.get(
                    f"{base_url}/v1/models",
                    headers=headers,
                    proxies=proxies,
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [item["id"] for item in data.get("data", []) if item.get("id")]
                return []

            # 4) OpenAI / OpenAI兼容
            if provider == "openai_compatible":
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                endpoints = ["/models"] if base_url.endswith("/v1") else ["/v1/models", "/models"]
                for endpoint in endpoints:
                    try:
                        resp = requests.get(
                            f"{base_url}{endpoint}",
                            headers=headers,
                            proxies=proxies,
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if "data" in data: return [item["id"] for item in data["data"] if item.get("id")]
                    except requests.exceptions.RequestException:
                        continue
                return []

        except Exception as e:
            logger.warning(f"Failed to fetch models from {provider} -> {base_url}: {e}")

        return []

    # =========================================================================
    # 调用参数组装
    # =========================================================================
    def build_kwargs(self, override_config: dict | None = None) -> dict:
        """
        统一组装 LiteLLM 参数。
        """
        self._prepare_proxy_env()

        from backend.settings import AIConfig

        raw_cfg = settings.config.ai
        cfg = AIConfig(**raw_cfg) if isinstance(raw_cfg, dict) else raw_cfg

        override_data = dict(override_config or {})

        if override_config:
            current_dict = asdict(cfg)
            # override_config 只覆盖“本次调用”的临时参数。
            # reasoning 相关字段已经不属于全局 AIConfig，避免在这里重新塞回 dataclass。
            filtered_override = {
                key: value
                for key, value in dict(override_config or {}).items()
                if key not in {"enable_reasoning", "reasoning_effort", "reasoning_mode"}
            }
            current_dict.update(filtered_override)
            cfg = AIConfig(**current_dict)

        provider = self._normalize_provider(getattr(cfg, "provider", "openai_compatible"))
        base_url = (getattr(cfg, "base_url", "") or DEFAULT_BASE_URLS.get(provider, "")).rstrip("/")
        endpoint_mode = (getattr(cfg, "endpoint_mode", "auto") or "auto").strip().lower()
        model_name = getattr(cfg, "model", "")
        capability_policy = self._resolve_model_capability_policy(model_name)
        requested_reasoning_mode = _normalize_reasoning_mode(override_data.get("reasoning_mode", ""))
        if "reasoning_mode" not in override_data and ("enable_reasoning" in override_data or "reasoning_effort" in override_data):
            if not bool(override_data.get("enable_reasoning", False)):
                requested_reasoning_mode = "off"
            elif "reasoning_effort" in override_data:
                requested_reasoning_mode = _normalize_reasoning_effort(override_data.get("reasoning_effort", "auto"))
            else:
                requested_reasoning_mode = "auto"

        kwargs = {
            "api_key": getattr(cfg, "api_key", "") or "dummy_key",
            "model": model_name,
            "_rmm_provider": provider,
            "_rmm_raw_model": model_name,
            "_rmm_base_url": base_url,
            "_rmm_endpoint_mode": endpoint_mode,
            "_rmm_reasoning_mode": requested_reasoning_mode,
            "_rmm_reasoning_effort": (
                requested_reasoning_mode
                if requested_reasoning_mode in {"low", "medium", "high", "xhigh"}
                else "auto"
            ),
        }

        if getattr(cfg, "temperature", None) is not None:
            kwargs["temperature"] = cfg.temperature

        if getattr(cfg, "max_tokens", None):
            kwargs["max_tokens"] = cfg.max_tokens

        # 深度思考只接受“本次调用显式覆盖”。
        # 不再从全局 AI 设置里自动继承 enable_reasoning，避免它重新变成全局开关。
        if (
            provider == "openai_compatible"
            and capability_policy
            and capability_policy.supports_reasoning
            and override_config is not None
            and (
                "reasoning_mode" in override_data
                or "enable_reasoning" in override_data
                or "reasoning_effort" in override_data
            )
        ):
            kwargs["_rmm_enable_reasoning"] = requested_reasoning_mode != "off"
            kwargs["_rmm_reasoning_mode"] = requested_reasoning_mode
            kwargs["_rmm_reasoning_effort"] = (
                requested_reasoning_mode
                if requested_reasoning_mode in {"low", "medium", "high", "xhigh"}
                else "auto"
            )

        if provider == "openai_compatible":
            # 对某些中转 / CF 盾保留浏览器头
            if base_url and not self._is_official_openai_base(base_url):
                kwargs["extra_headers"] = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            }

        elif provider == "anthropic":
            kwargs["model"] = f"anthropic/{cfg.model}"
        elif provider == "gemini":
            kwargs["model"] = f"gemini/{cfg.model}"
        elif provider == "ollama":
            kwargs["model"] = f"ollama/{cfg.model}"
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")

        if base_url:
            kwargs["api_base"] = base_url

        if settings.config.network.use_proxy_on_ai:
            proxy_url = network_mgr.get_proxy_url()
            if proxy_url:
                kwargs["proxy_url"] = proxy_url
        else:
            kwargs["proxy_url"] = None

        return kwargs

    # =========================================================================
    # OpenAI-compatible 私有兼容层
    # =========================================================================
    def _strip_private_meta(self, request_kwargs: dict) -> tuple[dict, dict]:
        """剥离内部元数据，得到真正可下发给 SDK / LiteLLM 的参数。"""
        kwargs = dict(request_kwargs)
        meta = {
            "provider": kwargs.pop("_rmm_provider", ""),
            "base_url": kwargs.pop("_rmm_base_url", ""),
            "raw_model": kwargs.pop("_rmm_raw_model", kwargs.get("model", "")),
            "endpoint_mode": kwargs.pop("_rmm_endpoint_mode", "auto"),
            "enable_reasoning": bool(kwargs.pop("_rmm_enable_reasoning", False)),
            "reasoning_mode": _normalize_reasoning_mode(kwargs.pop("_rmm_reasoning_mode", "off")),
            "reasoning_effort": _normalize_reasoning_effort(kwargs.pop("_rmm_reasoning_effort", "medium")),
        }
        # 后续 chat/responses 参数构造仍需要知道本次是否开启深度思考，
        # 因此在 meta 里留一份规范化后的逻辑开关，避免被上一步 pop 掉后丢失。
        kwargs["_rmm_enable_reasoning"] = meta["enable_reasoning"]
        kwargs["_rmm_reasoning_mode"] = meta["reasoning_mode"]
        kwargs["_rmm_reasoning_effort"] = meta["reasoning_effort"]
        return kwargs, meta

    def _sanitize_openai_compatible_params(self, request_kwargs: dict, meta: dict) -> tuple[dict, list[str]]:
        """清洗 OpenAI-compatible 调用参数，并返回兼容修正说明。"""
        kwargs = dict(request_kwargs)
        notes: list[str] = []

        # 这些字段不应该直接下发给 OpenAI SDK create(...)
        for key in ("proxy_url", "api_base", "custom_llm_provider"):
            kwargs.pop(key, None)

        if kwargs.get("temperature", None) is None:
            kwargs.pop("temperature", None)

        # GPT-5 兼容优先：不强塞 temperature
        if self._is_gpt5_family(meta["raw_model"]):
            temp = kwargs.get("temperature")
            if temp not in (None, 1, 1.0):
                kwargs.pop("temperature", None)
                notes.append(
                    f"检测到 {meta['raw_model']} 属于 GPT-5 家族，"
                    f"已自动移除 temperature={temp} 以避免兼容问题。"
                )

        return kwargs, notes

    def _is_reasoning_capability_error(self, error: Exception) -> bool:
        """识别“思考参数/能力不兼容”类错误，用于定向降级。"""
        text = str(error or "").lower()
        signals = (
            "reasoning",
            "reasoning_effort",
            "thinking",
            "enable_thinking",
            "does not support reasoning",
            "does not support thinking",
            "unsupported reasoning",
            "unsupported thinking",
            "invalid reasoning",
            "invalid thinking",
            "unknown parameter: reasoning",
            "unknown parameter: thinking",
            "unsupported parameter",
        )
        return any(signal in text for signal in signals)

    def _build_reasoning_fallback_requests(self, request_kwargs: dict) -> list[tuple[dict, str]]:
        """构造思考模式的降级重试链。"""
        if not bool(request_kwargs.get("_rmm_enable_reasoning", False)): return []

        mode = _normalize_reasoning_mode(request_kwargs.get("_rmm_reasoning_mode", "off"))
        candidates: list[tuple[dict, str]] = []
        if mode not in {"off", "auto"}:
            auto_kwargs = dict(request_kwargs)
            auto_kwargs["_rmm_enable_reasoning"] = True
            auto_kwargs["_rmm_reasoning_mode"] = "auto"
            auto_kwargs["_rmm_reasoning_effort"] = "auto"
            candidates.append((auto_kwargs, "当前模型不接受该思考等级，自动降级为“自动”后重试。"))

        off_kwargs = dict(request_kwargs)
        off_kwargs["_rmm_enable_reasoning"] = False
        off_kwargs["_rmm_reasoning_mode"] = "off"
        off_kwargs["_rmm_reasoning_effort"] = "auto"
        candidates.append((off_kwargs, "当前模型不接受思考参数，自动关闭思考后重试。"))

        normalized_candidates: list[tuple[dict, str]] = []
        seen: set[tuple[Any, ...]] = set()
        for candidate_kwargs, note in candidates:
            signature = (
                bool(candidate_kwargs.get("_rmm_enable_reasoning", False)),
                _normalize_reasoning_mode(candidate_kwargs.get("_rmm_reasoning_mode", "off")),
                _normalize_reasoning_effort(candidate_kwargs.get("_rmm_reasoning_effort", "auto")),
            )
            if signature in seen:
                continue
            seen.add(signature)
            normalized_candidates.append((candidate_kwargs, note))
        return normalized_candidates

    def _run_openai_reasoning_fallback_sync(self, runner, request_kwargs: dict):
        """仅在思考能力不兼容时做定向降级重试。"""
        try:
            return runner(dict(request_kwargs))
        except Exception as error:
            if not self._is_reasoning_capability_error(error):
                raise
            last_error = error
            for fallback_kwargs, note in self._build_reasoning_fallback_requests(request_kwargs):
                logger.warning(f"[openai_compatible] {note} error={last_error}")
                try:
                    return runner(dict(fallback_kwargs))
                except Exception as fallback_error:
                    if not self._is_reasoning_capability_error(fallback_error):
                        raise
                    last_error = fallback_error
            raise last_error

    async def _run_openai_reasoning_fallback_async(self, runner, request_kwargs: dict):
        """异步版本的思考能力定向降级重试。"""
        try:
            return await runner(dict(request_kwargs))
        except Exception as error:
            if not self._is_reasoning_capability_error(error):
                raise
            last_error = error
            for fallback_kwargs, note in self._build_reasoning_fallback_requests(request_kwargs):
                logger.warning(f"[openai_compatible] {note} error={last_error}")
                try:
                    return await runner(dict(fallback_kwargs))
                except Exception as fallback_error:
                    if not self._is_reasoning_capability_error(fallback_error):
                        raise
                    last_error = fallback_error
            raise last_error

    def _choose_openai_compatible_endpoint(self, meta: dict, stream: bool, tools, messages: list[dict] | None = None) -> str:
        """为 OpenAI-compatible 请求选择合适的 endpoint。

        选择原则：
        1. 含工具调用或 tool 消息时，必须走 chat.completions
        2. GPT-5 + OpenAI 官方优先走 responses
        3. 其余场景优先兼容 chat，不通再回退
        """
        mode = (meta.get("endpoint_mode") or "auto").lower()
        if self._messages_require_chat_completions(messages or []):
            return "chat_completions"
        if mode == "responses" and (stream or tools is not None):
            logger.warning("[openai_compatible] 当前 stream/tools 模式暂不走 responses，已自动改为 chat_completions。")
            return "chat_completions"
        if mode in ("chat_completions", "responses"):
            return mode

        # auto 模式
        if stream or tools is not None:
            return "chat_completions"

        # 官方 OpenAI + GPT-5，优先 responses
        capability_policy = self._resolve_model_capability_policy(meta["raw_model"])
        if capability_policy and capability_policy.prefer_responses and self._is_official_openai_base(meta["base_url"]):
            return "responses"

        # 默认先 chat，失败再回退 responses
        return "chat_completions"

    def _is_endpoint_mismatch_error(self, error: Exception) -> bool:
        """判断错误是否属于“这个模型/接口走错 endpoint”一类。"""
        code_candidates = (
            getattr(error, "code", None),
            getattr(getattr(error, "body", None), "code", None),
            getattr(getattr(error, "body", None), "error", None),
        )
        for code in code_candidates:
            if isinstance(code, dict):
                code = code.get("code") or code.get("type") or code.get("message")
            normalized_code = str(code or "").strip().lower()
            if normalized_code in {
                "model_not_supported",
                "unsupported_endpoint",
                "invalid_endpoint",
                "unsupported_model",
            }: return True

        text = str(error or "").lower()
        signals = (
            "unknown provider for model",
            "not supported on this endpoint",
            "chat.completions",
            "/v1/responses",
            "model_not_supported",
            "unsupported endpoint",
            "invalid url",
            "does not support this model",
            "only supported on responses",
            "only supported on chat",
        )
        return any(s in text for s in signals)

    def _should_fallback_openai_endpoint(
        self,
        *,
        messages: list[dict],
        stream: bool,
        tools: Any,
        error: Exception,
    ) -> bool:
        return (
            not stream
            and tools is None
            and self._is_endpoint_mismatch_error(error)
            and not self._messages_require_chat_completions(messages)
        )

    def _prepare_openai_compatible_request(self, messages: list[dict], request_kwargs: dict, meta: dict):
        """统一处理参数清洗与 endpoint 前置决策。"""
        request_kwargs, notes = self._sanitize_openai_compatible_params(request_kwargs, meta)
        self._log_openai_compatible_notes(notes)

        stream = bool(request_kwargs.pop("stream", False))
        tools = request_kwargs.pop("tools", None)
        tool_choice = request_kwargs.pop("tool_choice", None)
        num_retries = int(request_kwargs.pop("num_retries", 0) or 0)
        endpoint = self._choose_openai_compatible_endpoint(meta, stream, tools, messages)
        return request_kwargs, stream, tools, tool_choice, num_retries, endpoint

    def _run_openai_compatible_with_fallback_sync(
        self,
        *,
        messages: list[dict],
        stream: bool,
        tools: Any,
        num_retries: int,
        primary_label: str,
        fallback_label: str,
        primary_call,
        fallback_call,
    ):
        try:
            return self._call_with_retries_sync(primary_call, num_retries)
        except Exception as e:
            if self._should_fallback_openai_endpoint(messages=messages, stream=stream, tools=tools, error=e):
                logger.warning(f"[openai_compatible] {primary_label} 不可用，自动回退到 {fallback_label}: {e}")
                return self._call_with_retries_sync(fallback_call, num_retries)
            raise

    async def _run_openai_compatible_with_fallback_async(
        self,
        *,
        messages: list[dict],
        stream: bool,
        tools: Any,
        num_retries: int,
        primary_label: str,
        fallback_label: str,
        primary_call,
        fallback_call,
    ):
        try:
            return await self._call_with_retries_async(primary_call, num_retries)
        except Exception as e:
            if self._should_fallback_openai_endpoint(messages=messages, stream=stream, tools=tools, error=e):
                logger.warning(f"[openai_compatible] {primary_label} 不可用，自动回退到 {fallback_label}: {e}")
                return await self._call_with_retries_async(fallback_call, num_retries)
            raise

    def _build_openai_client_kwargs(self, request_kwargs: dict, meta: dict) -> dict:
        """统一构造 OpenAI SDK client 参数，避免同步/异步版本重复拼装。"""
        return {
            "api_key": request_kwargs.get("api_key") or "dummy_key",
            "base_url": (meta["base_url"] or DEFAULT_BASE_URLS["openai_compatible"]).rstrip("/"),
            "default_headers": request_kwargs.get("extra_headers") or None,
            "timeout": 60.0,
            "max_retries": 0,
        }

    def _create_openai_client(self, request_kwargs: dict, meta: dict) -> OpenAI:
        """创建同步 OpenAI SDK client。"""
        return OpenAI(**self._build_openai_client_kwargs(request_kwargs, meta))

    def _create_async_openai_client(self, request_kwargs: dict, meta: dict) -> AsyncOpenAI:
        """创建异步 OpenAI SDK client。"""
        return AsyncOpenAI(**self._build_openai_client_kwargs(request_kwargs, meta))

    async def _close_async_openai_client(self, client: Any) -> None:
        """尽力关闭异步 OpenAI client，避免底层 httpx 在 event loop 关闭后才延迟清理。"""
        if client is None: return

        close_callable = getattr(client, "close", None) or getattr(client, "aclose", None)
        if not callable(close_callable): return

        try:
            result = close_callable()
            if inspect.isawaitable(result):
                await result
        except RuntimeError as exc:
            logger.warning(f"[openai_compatible] 异步 client 关闭时事件循环已关闭: {exc}")
        except Exception as exc:
            logger.warning(f"[openai_compatible] 异步 client 关闭失败: {exc}")

    def _message_text(self, content: Any) -> str:
        """把 LiteLLM/OpenAI 风格的 content 统一压成纯文本。"""
        if content is None: return ""
        if isinstance(content, str): return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

    def _messages_require_chat_completions(self, messages: list[dict]) -> bool:
        """判断消息流里是否已经出现 tool-call 语义，从而强制走 chat.completions。"""
        for m in messages or []:
            if m.get("role") == "tool":
                return True
            if m.get("role") == "assistant" and m.get("tool_calls"):
                return True
        return False

    def _normalize_chat_messages_for_provider(self, messages: list[dict], meta: dict) -> list[dict]:
        """对 OpenAI-compatible chat 消息做最小兼容整理。

        目前主要处理 reasoning/thinking 模型的历史回灌：
        - 普通模型：忽略未知字段，不做额外处理
        - 已知需要 replay 的模型：保留 `reasoning_content`

        这样做的原因：
        - OpenAI 官方模型通常不依赖这个字段
        - 但 DeepSeek 等 thinking 模型在多轮工具调用里会强校验它是否被带回
        - 因此不能全局硬塞，也不能一刀切删除
        """
        raw_model = meta.get("raw_model", "")
        capability_policy = self._resolve_model_capability_policy(raw_model)
        keep_reasoning = bool(capability_policy and capability_policy.requires_reasoning_replay)
        normalized_messages: list[dict] = []

        for msg in messages or []:
            normalized = dict(msg)
            if not keep_reasoning:
                normalized.pop("reasoning_content", None)
            normalized_messages.append(normalized)

        return normalized_messages
    
    def _responses_input_from_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """把标准 chat messages 转为 Responses API 所需的 `instructions + input` 结构。"""
        instructions = "\n\n".join(
            self._message_text(m.get("content", ""))
            for m in messages
            if m.get("role") == "system"
        ).strip()

        input_messages: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue

            input_messages.append({
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": self._message_text(m.get("content", "")),
                    }
                ],
            })

        return instructions, input_messages

    def _wrap_text_response(self, text: str):
        """把 Responses API 的纯文本结果伪装成 chat.completions 兼容结构。"""
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )

    def _build_openai_chat_create_kwargs(
        self,
        messages: list[dict],
        request_kwargs: dict,
        meta: dict,
        *,
        stream: bool,
        tools=None,
        tool_choice=None,
    ) -> dict:
        """统一构造 chat.completions.create(...) 参数。"""
        capability_policy = self._resolve_model_capability_policy(meta["raw_model"])
        create_kwargs = {
            "model": meta["raw_model"],
            "messages": self._normalize_chat_messages_for_provider(messages, meta),
            "stream": stream,
        }

        if "temperature" in request_kwargs:
            create_kwargs["temperature"] = request_kwargs["temperature"]

        if request_kwargs.get("max_tokens"):
            create_kwargs["max_tokens"] = request_kwargs["max_tokens"]

        # OpenAI-compatible 没有统一的 thinking 开关字段。
        # 这里统一把“逻辑开关 + 强度”翻译成各模型真正接受的参数。
        enable_reasoning = bool(request_kwargs.pop("_rmm_enable_reasoning", False))
        reasoning_mode = _normalize_reasoning_mode(request_kwargs.pop("_rmm_reasoning_mode", "off"))
        reasoning_effort = _normalize_reasoning_effort(request_kwargs.pop("_rmm_reasoning_effort", "medium"))
        extra_body = dict(request_kwargs.get("extra_body") or {})

        if capability_policy and capability_policy.supports_reasoning:
            if "thinking" in (capability_policy.reasoning_extra_body or {}):
                # DeepSeek / Kimi / GLM / 豆包这类兼容层默认 thinking=enabled。
                # 如果用户关闭深度思考，必须显式传 disabled，否则服务端仍可能返回 reasoning_content。
                extra_body["thinking"] = {"type": "enabled" if enable_reasoning else "disabled"}
                if enable_reasoning:
                    if re.search(r"deepseek", meta["raw_model"], re.IGNORECASE) and reasoning_mode in {"low", "medium", "high", "xhigh"}:
                        deepseek_effort = "max" if reasoning_effort == "xhigh" else "high"
                        create_kwargs["reasoning_effort"] = deepseek_effort
            elif "enable_thinking" in (capability_policy.reasoning_extra_body or {}):
                # Qwen / QwQ 一类兼容层通常也走 extra_body。
                extra_body["enable_thinking"] = enable_reasoning
            elif "reasoning" in (capability_policy.reasoning_extra_body or {}):
                if enable_reasoning:
                    gpt_effort = "medium" if reasoning_mode == "auto" else ("high" if reasoning_effort == "xhigh" else reasoning_effort)
                    create_kwargs["reasoning"] = {"effort": gpt_effort}

        if extra_body:
            create_kwargs["extra_body"] = extra_body

        if tools is not None:
            create_kwargs["tools"] = tools
            if tool_choice is not None:
                create_kwargs["tool_choice"] = tool_choice

        return create_kwargs

    def _extract_responses_text(self, resp: Any) -> str:
        """从 Responses API 返回对象中提取最终文本。"""
        output_text = getattr(resp, "output_text", None)
        if output_text: return output_text

        parts = []
        for item in getattr(resp, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
                elif isinstance(content, dict) and content.get("text"):
                    parts.append(str(content["text"]))
        return "".join(parts)

    def _build_openai_responses_create_kwargs(self, messages: list[dict], request_kwargs: dict, meta: dict) -> dict:
        """统一构造 responses.create(...) 参数。"""
        capability_policy = self._resolve_model_capability_policy(meta["raw_model"])
        instructions, input_messages = self._responses_input_from_messages(messages)
        create_kwargs = {
            "model": meta["raw_model"],
            "input": input_messages or self._message_text(messages[-1].get("content", "")),
        }

        if instructions:
            create_kwargs["instructions"] = instructions

        if request_kwargs.get("max_tokens"):
            create_kwargs["max_output_tokens"] = request_kwargs["max_tokens"]

        # GPT-5 在 responses 接口下对 temperature 更敏感，默认不透传。
        if "temperature" in request_kwargs and not self._is_gpt5_family(meta["raw_model"]):
            create_kwargs["temperature"] = request_kwargs["temperature"]

        enable_reasoning = bool(request_kwargs.pop("_rmm_enable_reasoning", False))
        reasoning_mode = _normalize_reasoning_mode(request_kwargs.pop("_rmm_reasoning_mode", "off"))
        reasoning_effort = _normalize_reasoning_effort(request_kwargs.pop("_rmm_reasoning_effort", "medium"))

        # Responses 模式下目前主要服务 GPT-5。
        # 这里仍按统一逻辑开关处理，避免前端覆盖在 responses 路径失效。
        if capability_policy and capability_policy.supports_reasoning and "reasoning" in (capability_policy.reasoning_extra_body or {}):
            if enable_reasoning:
                gpt_effort = "medium" if reasoning_mode == "auto" else ("high" if reasoning_effort == "xhigh" else reasoning_effort)
                create_kwargs["reasoning"] = {"effort": gpt_effort}

        return create_kwargs

    def _call_openai_compatible_chat(
        self,
        messages: list[dict],
        request_kwargs: dict,
        meta: dict,
        *,
        stream: bool,
        tools=None,
        tool_choice=None
    ):
        """通过 OpenAI SDK 调用 `chat.completions.create(...)`。"""
        client = self._create_openai_client(request_kwargs, meta)
        create_kwargs = self._build_openai_chat_create_kwargs(
            messages,
            dict(request_kwargs),
            meta,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
        )
        return client.chat.completions.create(**create_kwargs)

    async def _call_openai_compatible_chat_async(
        self,
        messages: list[dict],
        request_kwargs: dict,
        meta: dict,
        *,
        stream: bool,
        tools=None,
        tool_choice=None
    ):
        """异步调用 `chat.completions.create(...)`。"""
        client = self._create_async_openai_client(request_kwargs, meta)
        try:
            create_kwargs = self._build_openai_chat_create_kwargs(
                messages,
                dict(request_kwargs),
                meta,
                stream=stream,
                tools=tools,
                tool_choice=tool_choice,
            )
            return await client.chat.completions.create(**create_kwargs)
        finally:
            await self._close_async_openai_client(client)

    def _call_openai_compatible_responses(self, messages: list[dict], request_kwargs: dict, meta: dict):
        """通过 OpenAI SDK 调用 `responses.create(...)` 并包成统一返回结构。"""
        client = self._create_openai_client(request_kwargs, meta)
        create_kwargs = self._build_openai_responses_create_kwargs(messages, dict(request_kwargs), meta)
        resp = client.responses.create(**create_kwargs)
        text = self._extract_responses_text(resp)
        return self._wrap_text_response(text)

    async def _call_openai_compatible_responses_async(self, messages: list[dict], request_kwargs: dict, meta: dict):
        """异步调用 `responses.create(...)` 并包成统一返回结构。"""
        client = self._create_async_openai_client(request_kwargs, meta)
        try:
            create_kwargs = self._build_openai_responses_create_kwargs(messages, dict(request_kwargs), meta)
            resp = await client.responses.create(**create_kwargs)
            text = self._extract_responses_text(resp)
            return self._wrap_text_response(text)
        finally:
            await self._close_async_openai_client(client)

    def _openai_compatible_completion(self, messages: list[dict], request_kwargs: dict, meta: dict):
        """OpenAI-compatible 同步入口，负责参数清洗、endpoint 选择和自动回退。"""
        request_kwargs, stream, tools, tool_choice, num_retries, endpoint = self._prepare_openai_compatible_request(
            messages,
            request_kwargs,
            meta,
        )

        def runner(active_request_kwargs: dict):
            """把 endpoint 路由决策封装进统一的 reasoning 降级流程。"""
            if endpoint == "responses":
                return self._run_openai_compatible_with_fallback_sync(
                    messages=messages,
                    stream=stream,
                    tools=tools,
                    num_retries=num_retries,
                    primary_label="/v1/responses",
                    fallback_label="/v1/chat/completions",
                    primary_call=lambda: self._call_openai_compatible_responses(messages, active_request_kwargs, meta),
                    fallback_call=lambda: self._call_openai_compatible_chat(
                        messages, active_request_kwargs, meta, stream=False, tools=None, tool_choice=None
                    ),
                )

            return self._run_openai_compatible_with_fallback_sync(
                messages=messages,
                stream=stream,
                tools=tools,
                num_retries=num_retries,
                primary_label="/v1/chat/completions",
                fallback_label="/v1/responses",
                primary_call=lambda: self._call_openai_compatible_chat(
                    messages, active_request_kwargs, meta, stream=stream, tools=tools, tool_choice=tool_choice
                ),
                fallback_call=lambda: self._call_openai_compatible_responses(messages, active_request_kwargs, meta),
            )

        return self._run_openai_reasoning_fallback_sync(runner, request_kwargs)

    async def _openai_compatible_acompletion(self, messages: list[dict], request_kwargs: dict, meta: dict):
        """OpenAI-compatible 异步入口，行为与同步版本保持一致。"""
        request_kwargs, stream, tools, tool_choice, num_retries, endpoint = self._prepare_openai_compatible_request(
            messages,
            request_kwargs,
            meta,
        )

        async def runner(active_request_kwargs: dict):
            """异步版 endpoint 路由封装，保持与同步入口相同的降级策略。"""
            if endpoint == "responses":
                return await self._run_openai_compatible_with_fallback_async(
                    messages=messages,
                    stream=stream,
                    tools=tools,
                    num_retries=num_retries,
                    primary_label="/v1/responses(Async)",
                    fallback_label="/v1/chat/completions",
                    primary_call=lambda: self._call_openai_compatible_responses_async(messages, active_request_kwargs, meta),
                    fallback_call=lambda: self._call_openai_compatible_chat_async(
                        messages, active_request_kwargs, meta, stream=False, tools=None, tool_choice=None
                    ),
                )

            return await self._run_openai_compatible_with_fallback_async(
                messages=messages,
                stream=stream,
                tools=tools,
                num_retries=num_retries,
                primary_label="/v1/chat/completions(Async)",
                fallback_label="/v1/responses",
                primary_call=lambda: self._call_openai_compatible_chat_async(
                    messages, active_request_kwargs, meta, stream=stream, tools=tools, tool_choice=tool_choice
                ),
                fallback_call=lambda: self._call_openai_compatible_responses_async(messages, active_request_kwargs, meta),
            )

        return await self._run_openai_reasoning_fallback_async(runner, request_kwargs)

    # =========================================================================
    # 公共调用接口
    # =========================================================================
    def completion(self, *, messages: list[dict], llm_kwargs: dict, **extra: Any):
        """同步调用统一入口。

        - `openai_compatible` 走本文件内部兼容层
        - 其他协议直接交给 LiteLLM
        """
        combined_kwargs = dict(llm_kwargs or {})
        combined_kwargs.update(extra)

        request_kwargs, meta = self._strip_private_meta(combined_kwargs)
        request_kwargs.pop("messages", None)

        logger.debug(f"AI调用，协议: {meta['provider']}，模型: {meta['raw_model']}，参数: {request_kwargs}, 消息: {messages}")
        
        if meta["provider"] == "openai_compatible":
            return self._openai_compatible_completion(messages, request_kwargs, meta)

        return litellm_completion(messages=messages, **request_kwargs)

    async def acompletion(self, *, messages: list[dict], llm_kwargs: dict, **extra: Any):
        """异步调用统一入口。"""
        combined_kwargs = dict(llm_kwargs or {})
        combined_kwargs.update(extra)

        request_kwargs, meta = self._strip_private_meta(combined_kwargs)
        request_kwargs.pop("messages", None)
        
        logger.debug(f"AI调用，协议: {meta['provider']}，模型: {meta['raw_model']}，参数: {request_kwargs}, 消息: {messages}")
        
        if meta["provider"] == "openai_compatible":
            return await self._openai_compatible_acompletion(messages, request_kwargs, meta)

        return await litellm_acompletion(messages=messages, **request_kwargs)

    # =========================================================================
    # Token 估算
    # =========================================================================
    def estimate_text_tokens(self, text: str, model_name: str) -> int:
        """估算单段文本的 Token 数；失败时回退到字符数近似估算。"""
        if not text:
            return 0
        try:
            return int(token_counter(model=model_name, text=text))
        except Exception as e:
            logger.debug(f"[AI诊断] 文本 Token 估算失败，改走字符兜底: {e}")
            return max(1, len(text) // 3)

    def estimate_messages_tokens(self, messages: list[dict], model_name: str) -> int:
        """估算整段 messages 的输入 Token；失败时退回文本拼接估算。"""
        if not messages:
            return 0
        try:
            return int(token_counter(model=model_name, messages=messages))
        except Exception as e:
            logger.debug(f"[AI诊断] Messages Token 估算失败，改走文本拼接兜底: {e}")
            merged_text = "\n".join(str(m.get("content", "")) for m in messages)
            return self.estimate_text_tokens(merged_text, model_name)
    
