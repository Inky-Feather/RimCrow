from __future__ import annotations

import errno
import re
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from backend.i18n.messages import tr


@dataclass(slots=True)
class AppError:
    error_type: str
    error_code: str
    message_key: str = ""
    message_params: dict[str, Any] = field(default_factory=dict)
    user_message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    error_id: str = ""
    message: str = ""
    data: Any = None


ErrorEnvelope = AppError

_ERROR_DETAIL_KEYS = ("traceback", "exception_type", "exception_module")


def _error_type_from_code(code: str = "", fallback: str = "SYSTEM") -> str:
    value = str(code or "").strip()
    if not value:
        return fallback
    return value.split(".", 1)[0] or fallback


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _extract_error_meta(value: Any) -> tuple[str, dict[str, Any]]:
    message_key = str(getattr(value, "message_key", "") or "").strip()
    params = getattr(value, "message_params", None)
    if isinstance(value, Mapping):
        message_key = str(value.get("message_key") or message_key).strip()
        params = value.get("message_params", params)
    return message_key, _normalize_mapping(params if isinstance(params, Mapping) else None)


def _iter_exception_chain(exc: BaseException | None, seen: set[int] | None = None):
    if exc is None:
        return
    if seen is None:
        seen = set()
    marker = id(exc)
    if marker in seen:
        return
    seen.add(marker)

    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException):
        yield from _iter_exception_chain(cause, seen)

    context = getattr(exc, "__context__", None)
    if isinstance(context, BaseException) and context is not cause:
        yield from _iter_exception_chain(context, seen)

    yield exc


def _exception_status_code(exc: BaseException) -> int | None:
    for attr in ("status_code",):
        raw = getattr(exc, attr, None)
        try:
            status = int(raw)
        except Exception:
            status = None
        if status:
            return status

    response = getattr(exc, "response", None)
    if response is not None:
        raw = getattr(response, "status_code", None)
        try:
            status = int(raw)
        except Exception:
            status = None
        if status:
            return status

    body = getattr(exc, "body", None)
    if body is not None:
        raw = getattr(body, "status_code", None)
        try:
            status = int(raw)
        except Exception:
            status = None
        if status:
            return status
    match = re.search(r"\b(?:status|code|error code)\D*(\d{3})\b|\b(\d{3})\s+Client Error\b", str(exc), re.IGNORECASE)
    if match:
        try:
            return int(match.group(1) or match.group(2))
        except Exception:
            return None
    return None


def _exception_text(exc: BaseException) -> str:
    parts = [str(exc or "").strip(), exc.__class__.__name__]
    module = getattr(exc.__class__, "__module__", "")
    if module:
        parts.append(module)
    response = getattr(exc, "response", None)
    if response is not None:
        url = getattr(response, "url", "")
        if url:
            parts.append(str(url))
        try:
            parts.append(str(getattr(response, "text", "") or ""))
        except Exception:
            pass
    return " ".join(part for part in parts if part)


def _response_url(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        url = getattr(response, "url", "")
        if url:
            return str(url)
        request = getattr(response, "request", None)
        url = getattr(request, "url", "") if request is not None else ""
        if url:
            return str(url)
    request = getattr(exc, "request", None)
    url = getattr(request, "url", "") if request is not None else ""
    return str(url or "")


def _infer_domain(module: str = "", action: str = "", context: Mapping[str, Any] | None = None, exc: BaseException | None = None) -> str:
    """基于调用域和请求目标判断错误归属，避免只靠原始报错文本串模块。"""
    module_text = str(module or "").strip().lower()
    action_text = str(action or "").strip().lower()
    if module_text.startswith("ai") or action_text.startswith("ai") or action_text in {"chat", "test_chat", "models"}:
        return "ai"
    if module_text.startswith(("git", "github")) or action_text.startswith(("git", "github")):
        return "git"
    if module_text.startswith(("steam", "workshop")) or action_text.startswith(("steam", "workshop")):
        return "steam"

    url_candidates = []
    if context:
        for key in ("url", "repo_url", "download_url", "base_url"):
            value = context.get(key)
            if value:
                url_candidates.append(str(value))
    if exc is not None:
        url_candidates.append(_response_url(exc))
    url_text = " ".join(url_candidates).lower()
    if any(host in url_text for host in ("github.com", "api.github.com", "gitlab.com", "gitgud.io")):
        return "git"
    if any(host in url_text for host in ("openai.com", "openrouter.ai", "anthropic.com", "generativelanguage.googleapis.com", "dashscope.aliyuncs.com", "siliconflow.cn")):
        return "ai"
    if "steamcommunity.com" in url_text or "steam" in url_text:
        return "steam"
    return ""


def _classify_http_status(status_code: int | None, domain: str = "", text: str = "") -> tuple[str, str, str, str]:
    lowered = str(text or "").lower()
    if status_code == 400:
        if domain == "ai":
            return _error_type_from_code("AI.REQUEST_INVALID"), "AI.REQUEST_INVALID", "errors.ai.request_invalid", tr("errors.ai.request_invalid", "AI 请求参数无效。请检查模型名称、Base URL、接口模式和高级参数。")
        return _error_type_from_code("NETWORK.REQUEST_INVALID"), "NETWORK.REQUEST_INVALID", "errors.network.request_invalid", tr("errors.network.request_invalid", "请求参数无效。请检查输入内容或配置后重试。")
    if status_code == 401:
        if domain == "ai":
            if "expired" in lowered or "过期" in lowered:
                return _error_type_from_code("AI.AUTH_EXPIRED"), "AI.AUTH_EXPIRED", "errors.ai.auth_expired", tr("errors.ai.auth_expired", "AI 登录令牌或 API Key 已过期。请重新填写密钥、刷新令牌或重新登录对应服务。")
            return _error_type_from_code("AI.AUTH_FAILED"), "AI.AUTH_FAILED", "errors.ai.auth_failed", tr("errors.ai.auth_failed", "API Key 无效或未被服务接受。请重新检查密钥、Base URL 和模型配置。")
        if domain == "git":
            return _error_type_from_code("GIT.AUTH_FAILED"), "GIT.AUTH_FAILED", "errors.git.auth_failed", tr("errors.git.auth_failed", "仓库服务认证失败。请检查登录状态、访问令牌或仓库访问权限。")
        return _error_type_from_code("NETWORK.AUTH_FAILED"), "NETWORK.AUTH_FAILED", "errors.network.auth_failed", tr("errors.network.auth_failed", "目标服务认证失败。请检查登录状态、访问令牌或请求配置。")
    if status_code == 403:
        if domain == "ai":
            return _error_type_from_code("AI.ACCESS_DENIED"), "AI.ACCESS_DENIED", "errors.ai.access_denied", tr("errors.ai.access_denied", "AI 服务拒绝访问。请检查账号权限、模型权限、额度和地区限制。")
        if domain == "git":
            return _error_type_from_code("GIT.ACCESS_DENIED"), "GIT.ACCESS_DENIED", "errors.git.access_denied", tr("errors.git.access_denied", "仓库资源没有访问权限。请检查登录状态、账号权限或仓库可见性。")
        return _error_type_from_code("NETWORK.ACCESS_DENIED"), "NETWORK.ACCESS_DENIED", "errors.network.access_denied", tr("errors.network.access_denied", "目标服务拒绝了请求。请检查登录状态、访问权限或请求配置。")
    if status_code == 404:
        if domain == "ai":
            return _error_type_from_code("AI.MODEL_NOT_FOUND"), "AI.MODEL_NOT_FOUND", "errors.ai.model_not_found", tr("errors.ai.model_not_found", "模型或接口路径不存在。请检查模型名称、Base URL 和接口地址。")
        if domain == "git":
            return _error_type_from_code("GIT.NOT_FOUND"), "GIT.NOT_FOUND", "errors.git.not_found", tr("errors.git.not_found", "仓库资源不存在、分支不存在或下载地址已失效。请检查链接、分支和访问权限。")
        return _error_type_from_code("NETWORK.NOT_FOUND"), "NETWORK.NOT_FOUND", "errors.network.not_found", tr("errors.network.not_found", "目标资源不存在或地址已失效。请检查链接、参数或稍后重试。")
    if status_code == 407:
        return _error_type_from_code("NETWORK.PROXY_AUTH"), "NETWORK.PROXY_AUTH", "errors.network.proxy_auth", tr("errors.network.proxy_auth", "代理服务器需要认证。请检查代理账号、密码或关闭不可用的代理。")
    if status_code == 408:
        return _error_type_from_code("NETWORK.TIMEOUT"), "NETWORK.TIMEOUT", "errors.network.timeout", tr("errors.network.timeout", "网络请求超时。请检查网络连接、代理设置或稍后重试。")
    if status_code == 429:
        if domain == "ai":
            return _error_type_from_code("AI.RATE_LIMIT"), "AI.RATE_LIMIT", "errors.ai.rate_limited", tr("errors.ai.rate_limited", "AI 请求过多或额度不足。请稍后重试，或检查账号额度与限速设置。")
        if domain == "git":
            return _error_type_from_code("GIT.RATE_LIMIT"), "GIT.RATE_LIMIT", "errors.git.rate_limited", tr("errors.git.rate_limited", "Git 资源请求过多。请稍后重试，或检查访问频率限制。")
        return _error_type_from_code("NETWORK.RATE_LIMIT"), "NETWORK.RATE_LIMIT", "errors.network.rate_limited", tr("errors.network.rate_limited", "请求过于频繁或服务限流。请稍后重试。")
    if status_code and 500 <= status_code < 600:
        if domain == "ai":
            return _error_type_from_code("AI.SERVICE_UNAVAILABLE"), "AI.SERVICE_UNAVAILABLE", "errors.ai.service_unavailable", tr("errors.ai.service_unavailable", "AI 服务暂时不可用。请稍后重试，或检查模型服务状态。")
        if domain == "git":
            return _error_type_from_code("GIT.SERVICE_UNAVAILABLE"), "GIT.SERVICE_UNAVAILABLE", "errors.git.service_unavailable", tr("errors.git.service_unavailable", "仓库服务暂时不可用。请稍后重试，或检查目标站点状态。")
        return _error_type_from_code("NETWORK.SERVICE_UNAVAILABLE"), "NETWORK.SERVICE_UNAVAILABLE", "errors.network.service_unavailable", tr("errors.network.service_unavailable", "目标服务暂时不可用。请稍后重试，或检查服务状态。")
    return "", "", "", ""


def _classify_ai_error_text(text: str = "") -> tuple[str, str, str, str]:
    lowered = str(text or "").lower()
    if not lowered:
        return "", "", "", ""
    if "unknown provider for model" in lowered:
        return _error_type_from_code("AI.ROUTING_FAILED"), "AI.ROUTING_FAILED", "errors.ai.routing_failed", tr("errors.ai.routing_failed", "当前代理接口无法正确路由这个模型。请检查模型名称、代理服务的模型映射，或切换接口模式后重试。")
    if "temperature" in lowered and ("unsupported" in lowered or "not support" in lowered or "不支持" in lowered):
        return _error_type_from_code("AI.PARAM_UNSUPPORTED"), "AI.PARAM_UNSUPPORTED", "errors.ai.param_unsupported", tr("errors.ai.param_unsupported", "当前模型不接受某些高级参数。请清空 temperature 等高级参数，或切换为自动兼容模式。")
    if ("choices" in lowered and ("empty" in lowered or "missing" in lowered)) or "non openai chat completions" in lowered:
        return _error_type_from_code("AI.RESPONSE_FORMAT"), "AI.RESPONSE_FORMAT", "errors.ai.response_format", tr("errors.ai.response_format", "AI 服务返回格式不兼容。请确认 Base URL、接口模式和模型协议是否匹配。")
    if "insufficient_quota" in lowered or "quota" in lowered:
        return _error_type_from_code("AI.RATE_LIMIT"), "AI.RATE_LIMIT", "errors.ai.rate_limited", tr("errors.ai.rate_limited", "AI 请求过多或额度不足。请稍后重试，或检查账号额度与限速设置。")
    return "", "", "", ""


def build_stack_detail(exc: BaseException, *, context: Mapping[str, Any] | None = None, error_id: str = "") -> dict[str, Any]:
    # detail 只给前端展示堆栈调试信息；业务上下文和错误 ID 走顶层字段或日志 extra_context。
    detail: dict[str, Any] = {
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        "exception_type": exc.__class__.__name__,
    }
    if getattr(exc, "__module__", ""):
        detail["exception_module"] = exc.__class__.__module__
    return detail


def _public_detail(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, Mapping):
        return {}
    payload: dict[str, Any] = {}
    for key in _ERROR_DETAIL_KEYS:
        value = detail.get(key)
        if value not in (None, ""):
            payload[key] = value
    return payload


def classify_exception(exc: BaseException, *, module: str = "", action: str = "", context: Mapping[str, Any] | None = None) -> AppError:
    error_type = "SYSTEM"
    error_code = "SYSTEM.UNKNOWN"
    message_key = ""
    message_params: dict[str, Any] = {}
    user_message = ""
    domain = _infer_domain(module, action, context, exc)

    try:
        import httpx
    except Exception:  # pragma: no cover - optional dependency guard
        httpx = None  # type: ignore[assignment]

    try:
        import requests
    except Exception:  # pragma: no cover - optional dependency guard
        requests = None  # type: ignore[assignment]

    try:
        from openai import AuthenticationError, APIConnectionError, RateLimitError, BadRequestError
    except Exception:  # pragma: no cover - optional dependency guard
        AuthenticationError = APIConnectionError = RateLimitError = BadRequestError = ()  # type: ignore[assignment]

    for current in _iter_exception_chain(exc):
        current_text = _exception_text(current)
        current_status = _exception_status_code(current)
        current_domain = _infer_domain(module, action, context, current) or domain
        class_name = current.__class__.__name__

        if current_domain == "ai":
            matched_type, matched_code, matched_key, matched_message = _classify_ai_error_text(current_text)
            if matched_code:
                error_type = matched_type
                error_code = matched_code
                message_key = matched_key
                user_message = matched_message
                break

        if isinstance(current, AuthenticationError):
            error_type, error_code, message_key, user_message = _classify_http_status(_exception_status_code(current) or 401, "ai", current_text)
            break
        if isinstance(current, RateLimitError):
            error_type, error_code, message_key, user_message = _error_type_from_code("AI.RATE_LIMIT"), "AI.RATE_LIMIT", "errors.ai.rate_limited", tr("errors.ai.rate_limited", "AI 请求过多或额度不足。请稍后重试，或检查账号额度与限速设置。")
            break
        if isinstance(current, APIConnectionError):
            error_type, error_code, message_key, user_message = _error_type_from_code("NETWORK.CONNECTION"), "NETWORK.CONNECTION", "errors.network.connection_failed", tr("errors.network.connection_failed", "无法连接到目标服务。请检查网络连接、代理设置或服务状态。")
            break
        if isinstance(current, (TimeoutError,)) or (requests and isinstance(current, requests.Timeout)) or (httpx and isinstance(current, httpx.TimeoutException)):
            error_type, error_code, message_key, user_message = _error_type_from_code("NETWORK.TIMEOUT"), "NETWORK.TIMEOUT", "errors.network.timeout", tr("errors.network.timeout", "网络请求超时。请检查网络连接、代理设置或稍后重试。")
            break
        if isinstance(current, PermissionError) or (isinstance(current, OSError) and getattr(current, "errno", None) in {errno.EACCES, errno.EPERM}):
            error_type, error_code, message_key, user_message = _error_type_from_code("SYSTEM.PERMISSION"), "SYSTEM.PERMISSION", "errors.system.permission_denied", tr("errors.system.permission_denied", "文件或目录权限不足。请关闭占用程序，或检查目标路径权限后重试。")
            break
        if class_name in {"ProxyError"}:
            error_type, error_code, message_key, user_message = _error_type_from_code("NETWORK.PROXY"), "NETWORK.PROXY", "errors.network.proxy_failed", tr("errors.network.proxy_failed", "代理连接失败。请检查代理地址、端口、账号密码，或临时关闭代理后重试。")
            break
        if isinstance(current, (ConnectionError,)) or (requests and isinstance(current, requests.ConnectionError)) or (httpx and isinstance(current, httpx.NetworkError)):
            error_type, error_code, message_key, user_message = _error_type_from_code("NETWORK.CONNECTION"), "NETWORK.CONNECTION", "errors.network.connection_failed", tr("errors.network.connection_failed", "无法连接到目标服务。请检查网络连接、代理设置或服务状态。")
            break
        if isinstance(current, BadRequestError):
            error_type, error_code, message_key, user_message = _error_type_from_code("AI.REQUEST_INVALID"), "AI.REQUEST_INVALID", "errors.ai.request_invalid", tr("errors.ai.request_invalid", "AI 请求参数无效。请检查模型名称、Base URL、接口模式和高级参数。")
            break
        if isinstance(current, ValueError) and current_domain == "ai":
            error_type, error_code, message_key, user_message = _error_type_from_code("AI.REQUEST_INVALID"), "AI.REQUEST_INVALID", "errors.ai.request_invalid", tr("errors.ai.request_invalid", "AI 请求参数无效。请检查模型名称、Base URL、接口模式和高级参数。")
            break
        if isinstance(current, ValueError):
            error_type, error_code, message_key, user_message = _error_type_from_code("SYSTEM.INVALID_INPUT"), "SYSTEM.INVALID_INPUT", "errors.system.invalid_input", tr("errors.system.invalid_input", "请求参数无效。请检查配置、输入内容或接口兼容性。")
            break

        if class_name in {"GithubRateLimitError"}:
            error_type, error_code, message_key, user_message = _error_type_from_code("GIT.RATE_LIMIT"), "GIT.RATE_LIMIT", "errors.git.rate_limited", tr("errors.git.rate_limited", "Git 资源请求过多。请稍后重试，或检查访问频率限制。")
            break
        if class_name in {"GithubApiError"}:
            lowered = current_text.lower()
            if "限流" in current_text or "rate limit" in lowered:
                error_type, error_code, message_key, user_message = _error_type_from_code("GIT.RATE_LIMIT"), "GIT.RATE_LIMIT", "errors.git.rate_limited", tr("errors.git.rate_limited", "Git 资源请求过多。请稍后重试，或检查访问频率限制。")
            elif "不存在" in current_text or "404" in current_text:
                error_type, error_code, message_key, user_message = _error_type_from_code("GIT.NOT_FOUND"), "GIT.NOT_FOUND", "errors.git.not_found", tr("errors.git.not_found", "仓库资源不存在、分支不存在或下载地址已失效。请检查链接、分支和访问权限。")
            else:
                error_type, error_code, message_key, user_message = _error_type_from_code("GIT.REQUEST_FAILED"), "GIT.REQUEST_FAILED", "errors.git.request_failed", tr("errors.git.request_failed", "Git 资源请求失败。请检查仓库地址、网络连接和访问权限。")
            break

        status_code = current_status or _exception_status_code(current)
        if status_code:
            matched_type, matched_code, matched_key, matched_message = _classify_http_status(status_code, current_domain, current_text)
            if matched_code:
                error_type = matched_type
                error_code = matched_code
                message_key = matched_key
                user_message = matched_message
                break

    return AppError(
        error_type=error_type,
        error_code=error_code,
        message_key=message_key,
        message_params=message_params,
        user_message=user_message,
        detail=build_stack_detail(exc, context=context),
    )


def coerce_error_envelope(
    error: Any,
    *,
    code: str = "",
    user_message: Any = "",
    message: Any = "",
    context: Mapping[str, Any] | None = None,
    detail: Any = None,
    message_key: str = "",
    message_params: Mapping[str, Any] | None = None,
    error_type: str = "",
    error_id: str = "",
    status: str = "error",
    data: Any = None,
) -> AppError:
    explicit_code = str(code or error_type or "").strip()
    if isinstance(error, AppError):
        envelope = error
    elif isinstance(error, Mapping):
        resolved_code = str(error.get("error_code") or explicit_code or error.get("error_type") or "APP.UNKNOWN").strip()
        envelope = AppError(
            error_type=str(error.get("error_type") or error_type or _error_type_from_code(resolved_code, "APP")).strip(),
            error_code=resolved_code,
            message_key=str(error.get("message_key") or message_key or "").strip(),
            message_params=_normalize_mapping(error.get("message_params") if isinstance(error.get("message_params"), Mapping) else message_params),
            user_message=str(error.get("user_message") or user_message or error.get("message") or message or "").strip(),
            detail=_public_detail(error.get("detail")),
            error_id=str(error.get("error_id") or error_id or "").strip(),
            message=str(error.get("message") or message or user_message or "").strip(),
            data=error.get("data", data),
        )
    elif isinstance(error, BaseException):
        envelope = classify_exception(error, module=str((context or {}).get("module", "")), action=str((context or {}).get("action", "")), context=context)
        envelope.error_id = error_id or envelope.error_id
        explicit_user_message = str(user_message or "").strip()
        if explicit_user_message:
            envelope.user_message = explicit_user_message
        elif not envelope.user_message:
            envelope.user_message = str(user_message or message or "").strip()
        envelope.message_key = str(message_key or envelope.message_key or "").strip()
        if message_params:
            envelope.message_params = dict(message_params)
        if data is not None:
            envelope.data = data
        if detail is not None:
            envelope.detail.update(_public_detail(detail))
        if (
            explicit_code
            and envelope.error_code.startswith("SYSTEM.")
            and not explicit_code.startswith(("SYSTEM.", "APP."))
        ):
            envelope.error_code = explicit_code
            envelope.error_type = _error_type_from_code(explicit_code, "APP")
    else:
        resolved_code = str(explicit_code or "APP.UNKNOWN").strip()
        envelope = AppError(
            error_type=str(error_type or _error_type_from_code(resolved_code, "APP")),
            error_code=resolved_code,
            message_key=str(message_key or "").strip(),
            message_params=_normalize_mapping(message_params),
            user_message=str(user_message or message or error or "").strip(),
            detail=_public_detail(detail),
            error_id=str(error_id or "").strip(),
            message=str(message or user_message or error or "").strip(),
            data=data,
        )

    if not envelope.error_type:
        envelope.error_type = str(error_type or _error_type_from_code(envelope.error_code, "APP"))
    elif "." in envelope.error_type:
        envelope.error_type = _error_type_from_code(envelope.error_type, "APP")
    if not envelope.error_code:
        envelope.error_code = str(code or envelope.error_type or "APP.UNKNOWN")
    if message_key:
        envelope.message_key = str(message_key).strip()
    if message_params:
        envelope.message_params = dict(message_params)
    if user_message and not envelope.user_message:
        envelope.user_message = str(user_message).strip()
    if message and not envelope.message:
        envelope.message = str(message).strip()
    if not envelope.message:
        envelope.message = envelope.user_message or envelope.message_key or envelope.error_code
    if envelope.detail:
        envelope.detail.setdefault("status", status)
    return envelope


def build_error_payload(envelope: AppError, *, status: str = "error") -> dict[str, Any]:
    detail = _public_detail(envelope.detail)
    payload = {
        "status": status,
        "message": envelope.message,
        "user_message": envelope.user_message,
        "data": envelope.data,
        "error_type": envelope.error_type,
        "error_code": envelope.error_code,
        "error_id": envelope.error_id,
    }
    if envelope.message_key:
        payload["message_key"] = envelope.message_key
    if envelope.message_params:
        payload["message_params"] = dict(envelope.message_params)
    if detail:
        payload["detail"] = detail
    return payload
