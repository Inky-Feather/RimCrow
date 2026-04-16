from __future__ import annotations

from typing import Any

from backend.utils.tools import normalize_package_id, normalize_workshop_id
from backend.utils.versioning import score_version_support


WORKSHOP_ID_MIN_LENGTH = 7
WORKSHOP_ID_MAX_LENGTH = 20


def normalize_cached_workshop_id(workshop_id: Any) -> str:
    """
    外置 Workshop 缓存相关逻辑使用更严格的 workshop_id 规范。

    这里比普通 `normalize_workshop_id()` 多一层约束：
    - 必须是纯数字
    - 长度必须落在 Steam 创意工坊 ID 的常见区间内
    """
    return normalize_workshop_id(
        workshop_id,
        digits_only=True,
        min_length=WORKSHOP_ID_MIN_LENGTH,
        max_length=WORKSHOP_ID_MAX_LENGTH,
    )


def _candidate_sort_key(current_game_version: str, candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    """
    为候选工坊详情生成排序键。

    排序优先级：
    1. 与当前游戏主版本是否匹配
    2. time_updated 越新越优先
    3. 有作者信息的条目略优先
    4. 最后用 workshop_id 保持确定性，避免同分情况下结果漂移
    """
    return (
        score_version_support(current_game_version, candidate.get("game_versions")),
        int(candidate.get("time_updated") or 0),
        1 if candidate.get("author") else 0,
        candidate.get("workshop_id") or "",
    )


def _build_meta_candidate(meta: dict[str, Any]) -> dict[str, Any] | None:
    """将 WorkshopMeta 记录整理成统一的候选结构。"""
    workshop_id = normalize_cached_workshop_id(meta.get("workshop_id"))
    if not workshop_id:
        return None
    return {
        "workshop_id": workshop_id,
        "package_id": normalize_package_id(meta.get("package_id")),
        "name": meta.get("title") or meta.get("name") or "",
        "author": meta.get("author"),
        "preview_url": meta.get("preview_url"),
        "time_updated": int(meta.get("time_updated") or 0),
        "game_versions": list(meta.get("game_versions") or []),
        "is_replacement_derived": False,
        "selection_reason": "meta",
    }


def _build_replacement_candidate(
    package_id: str,
    replacement: dict[str, Any],
    replacement_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """将 replacement 规则与可能存在的 replacement meta 合并为统一候选。"""
    workshop_id = normalize_cached_workshop_id(replacement.get("new_workshop_id"))
    if not workshop_id:
        return None

    if replacement_meta:
        return {
            "workshop_id": workshop_id,
            "package_id": normalize_package_id(
                replacement_meta.get("package_id") or replacement.get("new_package_id") or package_id
            ),
            "name": replacement_meta.get("title") or replacement_meta.get("name") or replacement.get("new_name") or "",
            "author": replacement_meta.get("author"),
            "preview_url": replacement_meta.get("preview_url"),
            "time_updated": int(replacement_meta.get("time_updated") or 0),
            "game_versions": list(replacement_meta.get("game_versions") or replacement.get("new_versions") or []),
            "is_replacement_derived": True,
            "selection_reason": "replacement_meta",
        }

    return {
        "workshop_id": workshop_id,
        "package_id": normalize_package_id(replacement.get("new_package_id") or package_id),
        "name": replacement.get("new_name") or "",
        "author": "",
        "preview_url": "",
        "time_updated": 0,
        "game_versions": list(replacement.get("new_versions") or []),
        "is_replacement_derived": True,
        "selection_reason": "replacement_rule",
    }


def _serialize_selected_candidate(
    normalized_package_id: str,
    candidate: dict[str, Any],
    candidate_count: int,
) -> dict[str, Any]:
    """将内部候选结构转换成对外返回结构。"""
    return {
        "package_id": candidate["package_id"] or normalized_package_id,
        "package_id_raw": candidate["package_id"] or normalized_package_id,
        "workshop_id": candidate["workshop_id"],
        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={candidate['workshop_id']}",
        "name": candidate["name"] or normalized_package_id,
        "author": [candidate["author"]] if candidate.get("author") else [],
        "preview_url": candidate.get("preview_url"),
        "is_replacement_derived": bool(candidate.get("is_replacement_derived")),
        "selection_reason": candidate.get("selection_reason"),
        "candidate_count": candidate_count,
    }


def select_best_workshop_detail_for_package(
    package_id: str,
    meta_candidates: list[dict[str, Any]] | None,
    replacement_candidates: list[dict[str, Any]] | None,
    replacement_meta_map: dict[str, dict[str, Any]] | None = None,
    current_game_version: str = "",
) -> dict[str, Any] | None:
    """
    为一个 package_id 选出“最适合作为 UI 补全结果”的 workshop 条目。

    当前策略刻意偏保守：
    - 如果 replacement 池里有候选，优先在 replacement 池中决策
    - 否则才使用同包名的原始 meta 候选
    - 版本匹配优先于更新时间
    """
    normalized_package_id = normalize_package_id(package_id)
    replacement_meta_map = replacement_meta_map or {}

    direct_pool: dict[str, dict[str, Any]] = {}
    for meta in meta_candidates or []:
        candidate = _build_meta_candidate(meta)
        if candidate:
            direct_pool[candidate["workshop_id"]] = candidate

    replacement_pool: dict[str, dict[str, Any]] = {}
    for replacement in replacement_candidates or []:
        replacement_meta = replacement_meta_map.get(normalize_cached_workshop_id(replacement.get("new_workshop_id")))
        candidate = _build_replacement_candidate(normalized_package_id, replacement, replacement_meta)
        if candidate:
            replacement_pool[candidate["workshop_id"]] = candidate

    pool = list(replacement_pool.values()) if replacement_pool else list(direct_pool.values())
    if not pool:
        return None

    best_candidate = max(pool, key=lambda candidate: _candidate_sort_key(current_game_version, candidate))
    return _serialize_selected_candidate(normalized_package_id, best_candidate, len(pool))
