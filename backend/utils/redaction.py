import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any


SENSITIVE_EXACT_KEYS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "steam_web_api_key",
}

SENSITIVE_SUFFIXES = (
    "_api_key",
    "_token",
    "_password",
    "_secret",
)

SENSITIVE_KEY_PARTS = (
    "access_token",
    "refresh_token",
)


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key or "").strip().lower()
    return (
        lowered in SENSITIVE_EXACT_KEYS
        or lowered.endswith(SENSITIVE_SUFFIXES)
        or any(part in lowered for part in SENSITIVE_KEY_PARTS)
    )


def mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return f"{text[:4]}...{text[-4:]}" if len(text) > 8 else "***"


def fingerprint_secret(value: Any, *, length: int = 16) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def redact_sensitive_data(value: Any, *, max_depth: int = 8) -> Any:
    """递归脱敏日志对象，保留普通结构，避免 API 参数日志泄露凭据。"""
    if max_depth <= 0:
        return "<max-depth>"
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            redacted[str(key)] = mask_secret(item) if is_sensitive_key(key) else redact_sensitive_data(item, max_depth=max_depth - 1)
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_sensitive_data(item, max_depth=max_depth - 1) for item in value]
    return value
