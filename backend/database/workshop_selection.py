from __future__ import annotations

import re
from typing import Any

from backend.utils.tools import normalize_package_id, normalize_workshop_id
from backend.utils.versioning import version_preference_key


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


def extract_workshop_id_from_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text: return ""
    if text.isdigit(): return normalize_cached_workshop_id(text)
    match = re.search(r"[?&]id=(\d{7,20})", text, re.IGNORECASE)
    return normalize_cached_workshop_id(match.group(1)) if match else ""


def _candidate_sort_key(current_game_version: str, candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int, str]:
    """
    为候选工坊详情生成排序键。

    排序优先级：
    1. 与当前游戏主版本是否匹配
    2. time_updated 越新越优先
    3. 有作者信息的条目略优先
    4. 最后用 workshop_id 保持确定性，避免同分情况下结果漂移
    """
    return (
        *version_preference_key(current_game_version, candidate.get("game_versions")),
        int(candidate.get("time_updated") or 0),
        1 if candidate.get("author") else 0,
        candidate.get("workshop_id", "") or "",
    )


def _build_meta_candidate(meta: dict[str, Any]) -> dict[str, Any] | None:
    """将 WorkshopMeta 记录整理成统一的候选结构。"""
    workshop_id = normalize_cached_workshop_id(meta.get("workshop_id"))
    if not workshop_id: return None
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
    if not workshop_id: return None

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


def _serialize_candidate(
    normalized_package_id: str,
    candidate: dict[str, Any],
    candidate_count: int = 0,
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
        "game_versions": list(candidate.get("game_versions") or []),
        "is_replacement_derived": bool(candidate.get("is_replacement_derived")),
        "selection_reason": candidate.get("selection_reason"),
        "candidate_count": candidate_count,
    }


def build_install_source(
    raw: dict[str, Any] | None,
    fallback_package_id: str = "",
    source_origin: str = "unknown",
    is_replacement: bool = False,
) -> dict[str, Any] | None:
    raw = raw or {}
    package_id = normalize_package_id(raw.get("package_id") or fallback_package_id)
    workshop_id = normalize_cached_workshop_id(
        raw.get("workshop_id") or raw.get("new_workshop_id") or extract_workshop_id_from_url(raw.get("url"))
    )
    raw_url = str(raw.get("url") or "").strip()
    supported_versions = list(raw.get("game_versions") or raw.get("supported_versions") or raw.get("new_versions") or [])
    title = str(raw.get("title") or raw.get("name") or raw.get("new_name") or package_id or workshop_id or raw_url).strip()

    if workshop_id:
        return {
            "kind": "workshop",
            "package_id": package_id,
            "workshop_id": workshop_id,
            "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}",
            "title": title or workshop_id,
            "supported_versions": supported_versions,
            "source_origin": source_origin,
            "is_replacement": is_replacement,
        }

    if not raw_url: return None

    return {
        "kind": "url",
        "package_id": package_id,
        "url": raw_url,
        "title": title or raw_url,
        "supported_versions": supported_versions,
        "source_origin": source_origin,
        "is_replacement": is_replacement,
    }


def dedupe_install_sources(sources) -> list[dict[str, Any]]:
    source_map: dict[str, dict[str, Any]] = {}
    for source in sources or []:
        normalized = build_install_source(
            source,
            fallback_package_id=source.get("package_id", "") if isinstance(source, dict) else "",
            source_origin=str(source.get("source_origin") or source.get("sourceOrigin") or "unknown") if isinstance(source, dict) else "unknown",
            is_replacement=bool(source.get("is_replacement")) if isinstance(source, dict) else False,
        )
        if not normalized:
            continue
        if normalized["kind"] == "workshop":
            key = f"workshop:{normalized['workshop_id']}"
        else:
            key = f"url:{normalized['url']}"
        source_map[key] = normalized
    return list(source_map.values())


def install_source_sort_key(current_game_version: str, source: dict[str, Any]) -> tuple[int, int, int, int, int, int, str]:
    return (
        *version_preference_key(current_game_version, source.get("supported_versions") or []),
        1 if source.get("kind") == "workshop" else 0,
        1 if source.get("source_origin") in {"asset", "import", "runtime"} else 0,
        source.get("workshop_id") or source.get("url") or "",
    )


def _select_best_candidate(
    candidates: list[dict[str, Any]] | None,
    current_game_version: str = "",
) -> dict[str, Any] | None:
    pool = list(candidates or [])
    if not pool: return None
    return max(pool, key=lambda candidate: _candidate_sort_key(current_game_version, candidate))


def select_best_workshop_detail_for_package(
    package_id: str,
    meta_candidates: list[dict[str, Any]] | None,
    replacement_candidates: list[dict[str, Any]] | None,
    replacement_meta_map: dict[str, dict[str, Any]] | None = None,
    current_game_version: str = "",
) -> dict[str, Any] | None:
    lookup = build_workshop_detail_lookup(
        package_id,
        meta_candidates=meta_candidates,
        replacement_candidates=replacement_candidates,
        replacement_meta_map=replacement_meta_map,
        current_game_version=current_game_version,
    )
    return (lookup.get("display") or {}).get("selected")


def build_workshop_detail_lookup(
    package_id: str,
    meta_candidates: list[dict[str, Any]] | None,
    replacement_candidates: list[dict[str, Any]] | None,
    replacement_meta_map: dict[str, dict[str, Any]] | None = None,
    current_game_version: str = "",
) -> dict[str, Any]:
    """
    返回 package_id 对应的精细化候选结构。

    语义约定：
    - direct: 仅表示按同 package_id 直接查到的原版候选
    - replacement: 仅表示 replacement 规则命中的替代候选
    - display: 仅供 UI 兜底展示使用，优先 replacement，其次 direct
    """
    normalized_package_id = normalize_package_id(package_id)
    replacement_meta_map = replacement_meta_map or {}

    replacement_pool: dict[str, dict[str, Any]] = {}
    for replacement in replacement_candidates or []:
        replacement_meta = replacement_meta_map.get(normalize_cached_workshop_id(replacement.get("new_workshop_id")))
        candidate = _build_replacement_candidate(normalized_package_id, replacement, replacement_meta)
        if candidate:
            replacement_pool[candidate["workshop_id"]] = candidate

    replacement_workshop_ids = set(replacement_pool.keys())
    direct_pool: dict[str, dict[str, Any]] = {}
    for meta in meta_candidates or []:
        candidate = _build_meta_candidate(meta)
        if not candidate:
            continue
        if candidate["workshop_id"] in replacement_workshop_ids:
            continue
        direct_pool[candidate["workshop_id"]] = candidate

    direct_candidates = [
        _serialize_candidate(normalized_package_id, candidate, len(direct_pool))
        for candidate in direct_pool.values()
    ]
    replacement_candidates_serialized = [
        _serialize_candidate(normalized_package_id, candidate, len(replacement_pool))
        for candidate in replacement_pool.values()
    ]

    direct_selected_raw = _select_best_candidate(list(direct_pool.values()), current_game_version=current_game_version)
    replacement_selected_raw = _select_best_candidate(list(replacement_pool.values()), current_game_version=current_game_version)

    direct_selected = (
        _serialize_candidate(normalized_package_id, direct_selected_raw, len(direct_pool))
        if direct_selected_raw else None
    )
    replacement_selected = (
        _serialize_candidate(normalized_package_id, replacement_selected_raw, len(replacement_pool))
        if replacement_selected_raw else None
    )

    display_selected = replacement_selected or direct_selected
    if replacement_selected:
        display_selected_from = "replacement"
    elif direct_selected:
        display_selected_from = "direct"
    else:
        display_selected_from = "none"

    return {
        "package_id": normalized_package_id,
        "direct": {
            "candidates": direct_candidates,
            "selected": direct_selected,
        },
        "replacement": {
            "candidates": replacement_candidates_serialized,
            "selected": replacement_selected,
        },
        "display": {
            "selected": display_selected,
            "selected_from": display_selected_from,
        },
    }
