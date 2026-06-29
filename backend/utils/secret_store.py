from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.utils.redaction import mask_secret

try:
    import keyring
except Exception:  # pragma: no cover - 依赖损坏时走运行时错误路径
    keyring = None


logger = logging.getLogger(__name__)
MISSING_SECRET_ERROR_MARKERS = (
    "not found",
    "no password",
    "not present",
    "not exist",
    "could not be found",
    "不存在",
    "找不到",
    "未找到",
)

SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "ai.api_key": ("ai", "api_key"),
    "steam.web_api_key": ("steam_web_api_key",),
    "network.proxy.username": ("network", "proxy", "username"),
    "network.proxy.password": ("network", "proxy", "password"),
}


class SecretStoreError(RuntimeError):
    pass


@dataclass
class SecretStatus:
    key: str
    has_value: bool
    hint: str = ""
    available: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "has_value": self.has_value,
            "hint": self.hint,
            "available": self.available,
            "error": self.error,
        }


class SecretStore:
    """跨平台凭据存储封装，真实密钥只写入系统凭据后端。"""

    def __init__(self, service_name: str = "RimModManager", backend: Any = None):
        self.service_name = service_name
        self._backend = backend
        self.last_error = ""
        self.fallback_keys: set[str] = set()
        self.fallback_errors: dict[str, str] = {}

    @property
    def backend(self):
        return self._backend or keyring

    def _fail(self, message: str, exc: Exception | None = None) -> SecretStoreError:
        self.last_error = message
        if exc:
            logger.warning("SecretStore 处理失败：%s", message, exc_info=True)
        return SecretStoreError(message)

    def _is_missing_secret_error(self, exc: Exception) -> bool:
        text = f"{type(exc).__name__} {exc}".lower()
        return any(marker in text for marker in MISSING_SECRET_ERROR_MARKERS)

    def validate_key(self, key: str) -> str:
        normalized = str(key or "").strip()
        if normalized not in SECRET_FIELDS:
            raise SecretStoreError("不支持的密钥项")
        return normalized

    def get_secret(self, key: str) -> str:
        normalized = self.validate_key(key)
        backend = self.backend
        if backend is None:
            self.last_error = "系统凭据库不可用"
            return ""
        try:
            value = backend.get_password(self.service_name, normalized)
            self.last_error = ""
            return str(value or "")
        except Exception as exc:
            self.last_error = str(exc) or "系统凭据库读取失败"
            logger.warning("读取系统凭据失败: %s", normalized, exc_info=True)
            return ""

    def set_secret(self, key: str, value: str) -> None:
        normalized = self.validate_key(key)
        text = str(value or "")
        backend = self.backend
        if backend is None:
            raise self._fail("本机安全存储不可用，请检查系统凭据服务后重试")
        try:
            if text:
                backend.set_password(self.service_name, normalized, text)
            else:
                self.delete_secret(normalized)
            self.fallback_keys.discard(normalized)
            self.fallback_errors.pop(normalized, None)
            self.last_error = ""
        except Exception as exc:
            raise self._fail("无法保存密钥，请确认本机安全存储可用后重试", exc) from exc

    def delete_secret(self, key: str) -> None:
        normalized = self.validate_key(key)
        backend = self.backend
        if backend is None:
            raise self._fail("本机安全存储不可用，请检查系统凭据服务后重试")
        try:
            if not backend.get_password(self.service_name, normalized):
                self.fallback_keys.discard(normalized)
                self.fallback_errors.pop(normalized, None)
                self.last_error = ""
                return
            backend.delete_password(self.service_name, normalized)
            self.fallback_keys.discard(normalized)
            self.fallback_errors.pop(normalized, None)
            self.last_error = ""
        except Exception as exc:
            # keyring 删除不存在的项时不同后端表现不一致；对用户来说最终状态已经是“未保存”。
            if self._is_missing_secret_error(exc):
                self.last_error = ""
                return
            raise self._fail("无法删除已保存密钥，请确认本机安全存储可用后重试", exc) from exc

    def status(self, key: str, fallback_value: str = "") -> SecretStatus:
        normalized = self.validate_key(key)
        value = self.get_secret(normalized)
        fallback_error = self.fallback_errors.get(normalized, "")
        available = not bool(self.last_error or fallback_error)
        effective_value = value or str(fallback_value or "")
        return SecretStatus(
            key=normalized,
            has_value=bool(effective_value),
            hint=mask_secret(effective_value),
            available=available,
            error="" if available else (fallback_error or self.last_error),
        )

    def status_map(self, runtime_config: Any = None) -> dict[str, dict[str, Any]]:
        return {
            key: self.status(key, _get_nested_value(runtime_config, path)).to_dict()
            for key, path in SECRET_FIELDS.items()
        }

    def migrate_and_hydrate(self, runtime_config: Any) -> bool:
        """
        旧配置里如果还有明文，优先写入系统凭据库；随后把可读取的凭据回灌到运行时配置。
        返回值表示是否成功把至少一项旧明文迁移进凭据库。
        """
        changed = False
        for key, path in SECRET_FIELDS.items():
            plaintext = str(_get_nested_value(runtime_config, path) or "")
            stored = self.get_secret(key)
            if plaintext:
                try:
                    self.set_secret(key, plaintext)
                    stored = plaintext
                    changed = True
                except SecretStoreError:
                    # 写入失败时保留旧配置明文；下次启动会继续尝试迁移，避免静默丢失。
                    self.fallback_keys.add(key)
                    self.fallback_errors[key] = "本机安全存储不可用，密钥暂时保留在配置文件中"
                    stored = plaintext
            if stored:
                _set_nested_value(runtime_config, path, stored)
        return changed

    def apply_secret_inputs(self, runtime_config: Any, data: dict[str, Any]) -> bool:
        """保存设置表单中的密钥：有值则更新，空值则删除；读取失败的字段由前端显式标记保留。"""
        changed = False
        preserve_keys = {self.validate_key(key) for key in (data.pop("_preserve_secret_keys", []) or [])}
        for key, path in SECRET_FIELDS.items():
            present, value = _pop_nested_value(data, path)
            if not present:
                continue
            text = str(value or "")
            if text:
                self.set_secret(key, text)
                _set_nested_value(runtime_config, path, text)
                changed = True
            elif key in preserve_keys:
                continue
            elif not str(_get_nested_value(runtime_config, path) or ""):
                continue
            else:
                self.delete_secret(key)
                _set_nested_value(runtime_config, path, "")
                changed = True
        return changed

    def clear_runtime_secret(self, runtime_config: Any, key: str) -> None:
        normalized = self.validate_key(key)
        _set_nested_value(runtime_config, SECRET_FIELDS[normalized], "")


def _get_nested_value(root: Any, path: tuple[str, ...]) -> Any:
    current = root
    for segment in path:
        if current is None:
            return ""
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            current = getattr(current, segment, None)
    return current


def _set_nested_value(root: Any, path: tuple[str, ...], value: Any) -> None:
    current = root
    for segment in path[:-1]:
        if isinstance(current, dict):
            current = current.setdefault(segment, {})
        else:
            current = getattr(current, segment)
    if isinstance(current, dict):
        current[path[-1]] = value
    else:
        setattr(current, path[-1], value)


def _pop_nested_value(root: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = root
    for segment in path[:-1]:
        if not isinstance(current, dict) or segment not in current:
            return False, None
        current = current.get(segment)
    if not isinstance(current, dict) or path[-1] not in current:
        return False, None
    return True, current.pop(path[-1])


secret_store = SecretStore()
