from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.utils.tools import normalize_package_id


STEAM_SUFFIX = "_steam"
LOCAL_SUFFIX = "_local"


@dataclass(slots=True, frozen=True)
class PackageTokenInfo:
    raw_token: str
    normalized_token: str
    canonical_package_id: str
    source_preference: str


def parse_package_token(value: Any) -> PackageTokenInfo:
    """
    解析加载顺序层的包名 token。

    这里的 token 只服务于 ModsConfig / active list 等“来源选择”场景：
    - `author.mod`        -> 裸包名，默认来源
    - `author.mod_steam`  -> 强制工坊来源
    - `author.mod_local`  -> 兼容读取，视为本地族来源
    """

    raw_token = str(value or "").strip()
    normalized_token = raw_token.lower()
    if not normalized_token:
        return PackageTokenInfo("", "", "", "any")

    if normalized_token.endswith(STEAM_SUFFIX):
        canonical = normalize_package_id(normalized_token[: -len(STEAM_SUFFIX)])
        return PackageTokenInfo(raw_token, normalized_token, canonical, "steam")

    if normalized_token.endswith(LOCAL_SUFFIX):
        canonical = normalize_package_id(normalized_token[: -len(LOCAL_SUFFIX)])
        return PackageTokenInfo(raw_token, normalized_token, canonical, "local")

    canonical = normalize_package_id(normalized_token)
    return PackageTokenInfo(raw_token, normalized_token, canonical, "any")


def strip_package_token_suffix(value: Any) -> str:
    return parse_package_token(value).canonical_package_id


def is_steam_package_token(value: Any) -> bool:
    return parse_package_token(value).source_preference == "steam"


def build_steam_package_token(package_id: Any) -> str:
    canonical = strip_package_token_suffix(package_id)
    return f"{canonical}{STEAM_SUFFIX}" if canonical else ""


def select_mod_instance(mod_record: dict[str, Any] | None, package_token: Any) -> dict[str, Any]:
    """按加载顺序 token 选择实际模组实例，并保留规范包名用于规则匹配。

    这里集中处理共存模组的来源选择。调用方不应再自行展开
    ``coexist_workshop_variant``，否则很容易在读取原生规则前丢失来源信息。
    返回副本，避免把临时的实例字段写回数据库查询结果。
    """
    if not isinstance(mod_record, dict):
        return {}

    token_info = parse_package_token(package_token or mod_record.get("package_id"))
    canonical_id = token_info.canonical_package_id
    if not canonical_id:
        return {}

    selected = dict(mod_record)
    raw_variant = mod_record.get("coexist_workshop_variant")
    is_workshop = False
    if token_info.source_preference == "steam" and isinstance(raw_variant, dict):
        is_workshop = True
        for key, value in raw_variant.items():
            selected[str(key)] = value

    selected["package_id"] = canonical_id
    selected["canonical_package_id"] = canonical_id
    selected["active_package_token"] = token_info.normalized_token if is_workshop else canonical_id
    selected["source_preference"] = "steam" if is_workshop else "local"
    selected["is_coexistence"] = bool(is_workshop)
    return selected
