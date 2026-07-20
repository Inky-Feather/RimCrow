from __future__ import annotations

import errno
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


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


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _extract_error_meta(value: Any) -> tuple[str, dict[str, Any]]:
    message_key = str(getattr(value, "message_key", "") or "").strip()
    params = getattr(value, "message_params", None)
    if isinstance(value, Mapping):
        message_key = str(value.get("message_key") or message_key).strip()
        params = value.get("message_params", params)
    return message_key, _normalize_mapping(params if isinstance(params, Mapping) else None)


def build_stack_detail(exc: BaseException, *, context: Mapping[str, Any] | None = None, error_id: str = "") -> dict[str, Any]:
    detail: dict[str, Any] = {
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        "exception_type": exc.__class__.__name__,
    }
    if getattr(exc, "__module__", ""):
        detail["exception_module"] = exc.__class__.__module__
    if context:
        detail["context"] = dict(context)
    if error_id:
        detail["error_id"] = error_id
    return detail


def classify_exception(exc: BaseException, *, module: str = "", action: str = "", context: Mapping[str, Any] | None = None) -> AppError:
    error_type = "SYSTEM.UNKNOWN"
    error_code = "SYSTEM.UNKNOWN"
    message_key = ""
    message_params: dict[str, Any] = {}
    user_message = ""

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

    if isinstance(exc, AuthenticationError):
        error_type = error_code = "AI.AUTH"
        message_key = "errors.ai.auth_failed"
    elif isinstance(exc, RateLimitError):
        error_type = error_code = "AI.RATE_LIMIT"
        message_key = "errors.ai.rate_limited"
    elif isinstance(exc, (TimeoutError,)) or (requests and isinstance(exc, requests.Timeout)) or (httpx and isinstance(exc, httpx.TimeoutException)):
        error_type = error_code = "NETWORK.TIMEOUT"
        message_key = "errors.network.timeout"
    elif isinstance(exc, PermissionError) or (isinstance(exc, OSError) and getattr(exc, "errno", None) in {errno.EACCES, errno.EPERM}):
        error_type = error_code = "SYSTEM.PERMISSION"
        message_key = "errors.system.permission_denied"
    elif isinstance(exc, (ConnectionError,)) or (requests and isinstance(exc, requests.ConnectionError)) or (httpx and isinstance(exc, httpx.NetworkError)):
        error_type = error_code = "NETWORK.CONNECTION"
        message_key = "errors.network.connection_failed"
    elif isinstance(exc, (BadRequestError, ValueError)):
        error_type = error_code = "SYSTEM.INVALID_INPUT"
        message_key = "errors.system.invalid_input"
    elif isinstance(exc, APIConnectionError):
        error_type = error_code = "NETWORK.CONNECTION"
        message_key = "errors.network.connection_failed"

    meta: dict[str, Any] = {}
    if module:
        meta["module"] = module
    if action:
        meta["action"] = action
    if context:
        meta["context"] = dict(context)
    if meta:
        message_params = meta

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
    if isinstance(error, AppError):
        envelope = error
    elif isinstance(error, Mapping):
        envelope = AppError(
            error_type=str(error.get("error_type") or error_type or code or "APP.UNKNOWN"),
            error_code=str(error.get("error_code") or code or error.get("error_type") or "APP.UNKNOWN"),
            message_key=str(error.get("message_key") or message_key or "").strip(),
            message_params=_normalize_mapping(error.get("message_params") if isinstance(error.get("message_params"), Mapping) else message_params),
            user_message=str(error.get("user_message") or user_message or error.get("message") or message or "").strip(),
            detail=_normalize_mapping(error.get("detail") if isinstance(error.get("detail"), Mapping) else None),
            error_id=str(error.get("error_id") or error_id or "").strip(),
            message=str(error.get("message") or message or user_message or "").strip(),
            data=error.get("data", data),
        )
    elif isinstance(error, BaseException):
        envelope = classify_exception(error, module=str((context or {}).get("module", "")), action=str((context or {}).get("action", "")), context=context)
        envelope.error_id = error_id or envelope.error_id
        envelope.data = data
        envelope.user_message = str(user_message or message or envelope.user_message or "").strip()
        envelope.message_key = str(message_key or envelope.message_key or "").strip()
        if message_params:
            envelope.message_params = dict(message_params)
        if detail is not None and isinstance(detail, Mapping):
            envelope.detail.update(dict(detail))
    else:
        resolved_code = str(code or error_type or "APP.UNKNOWN").strip()
        envelope = AppError(
            error_type=str(error_type or resolved_code.split(".", 1)[0] or "APP.UNKNOWN"),
            error_code=resolved_code,
            message_key=str(message_key or "").strip(),
            message_params=_normalize_mapping(message_params),
            user_message=str(user_message or message or error or "").strip(),
            detail=_normalize_mapping(detail if isinstance(detail, Mapping) else None),
            error_id=str(error_id or "").strip(),
            message=str(message or user_message or error or "").strip(),
            data=data,
        )

    if context:
        envelope.detail.setdefault("context", dict(context))
    if not envelope.error_type:
        envelope.error_type = str(error_type or envelope.error_code or "APP.UNKNOWN").split(".", 1)[0] or "APP.UNKNOWN"
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
    envelope.detail.setdefault("status", status)
    return envelope


def build_error_payload(envelope: AppError, *, status: str = "error") -> dict[str, Any]:
    payload = {
        "status": status,
        "message": envelope.message,
        "data": envelope.data,
        "error_type": envelope.error_type,
        "error_code": envelope.error_code,
        "error_id": envelope.error_id,
    }
    if envelope.message_key:
        payload["message_key"] = envelope.message_key
    if envelope.message_params:
        payload["message_params"] = dict(envelope.message_params)
    if envelope.detail:
        payload["detail"] = dict(envelope.detail)
    return payload
