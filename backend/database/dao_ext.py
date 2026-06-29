from __future__ import annotations

import re
from typing import Any

from peewee import JOIN, fn
from playhouse.shortcuts import model_to_dict

from backend.database.models import ModAsset
from backend.database.models_ext import ModReplacement, WorkshopAuthorCache, WorkshopManifest, WorkshopOnlineCache
from backend.database.workshop_selection import (
    build_install_source,
    build_workshop_detail_lookup,
    dedupe_install_sources,
    install_source_sort_key,
    normalize_cached_workshop_id,
)
from backend.utils.constants import steam_appids_to_rimworld_package_ids
from backend.utils.tools import normalize_package_id, normalize_package_ids
from backend.utils.versioning import score_version_support


def _require_database_dependencies() -> None:
    """确保数据库相关依赖可用。"""
    if (
        model_to_dict is None
        or fn is None
        or WorkshopManifest is None
        or WorkshopOnlineCache is None
        or WorkshopAuthorCache is None
        or ModReplacement is None
        or ModAsset is None
    ):
        raise ModuleNotFoundError("dao_ext database dependencies are unavailable")


def _normalize_author_profile(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """把作者缓存行压缩成前端可直接展示的稳定结构。"""
    if not row:
        return None
    steam_id = str(row.get("steam_id") or "").strip()
    if not steam_id:
        return None
    return {
        "steam_id": steam_id,
        "name": str(row.get("personaname") or "").strip(),
        "profile_url": str(row.get("profile_url") or "").strip(),
        "avatar": str(row.get("avatar") or "").strip(),
        "country_code": str(row.get("country_code") or "").strip(),
        "time_created": int(row.get("time_created") or 0),
    }


def _get_author_cache_map(steam_ids: list[str]) -> dict[str, dict[str, Any]]:
    """批量读取作者资料缓存；表缺失时降级为空，避免影响旧库启动。"""
    normalized_ids = []
    seen_ids: set[str] = set()
    for steam_id in steam_ids or []:
        normalized_id = str(steam_id or "").strip()
        if not normalized_id or normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)
        normalized_ids.append(normalized_id)
    if not normalized_ids:
        return {}
    try:
        rows = (
            WorkshopAuthorCache.select()
            .where(WorkshopAuthorCache.steam_id.in_(normalized_ids))
            .dicts()
        )
        return {
            str(row["steam_id"]): profile
            for row in rows
            if (profile := _normalize_author_profile(row))
        }
    except Exception:
        return {}


def _merge_manifest_with_online(manifest: dict[str, Any] | None, online: dict[str, Any] | None ) -> dict[str, Any]:
    """
    将文件快照层与在线缓存层合并成查询层使用的统一结构。

    合并原则：
    - 身份与依赖字段来自 manifest；
    - 展示增强字段优先取 online；
    - online 缺失时回退到 manifest，保持查询结果稳定。
    """
    manifest = manifest or {}
    online = online or {}
    workshop_id = str(
        online.get("workshop_id")
        or manifest.get("workshop_id")
        or ""
    ).strip()
    author_profile = _normalize_author_profile(online.get("author_profile") if isinstance(online.get("author_profile"), dict) else None)
    if author_profile is None:
        author_profile = _get_author_cache_map([online.get("author_steam_id","")]).get(str(online.get("author_steam_id","") or "").strip())
    author_name = manifest.get("author") or (author_profile or {}).get("name") or ""
    stats = online.get("stats") if isinstance(online.get("stats"), dict) else {}
    return {
        "workshop_id": workshop_id,
        "package_id": manifest.get("package_id"),
        "name": manifest.get("name"),
        "title": online.get("title") or manifest.get("name"),
        "author": author_name,
        "author_steam_id": online.get("author_steam_id"),
        "author_profile": author_profile,
        "game_versions": manifest.get("game_versions") or [],
        "dependencies_mods": manifest.get("dependencies_mods") or {},
        "short_description": online.get("short_description"),
        "description": online.get("description"),
        "preview_url": online.get("preview_url"),
        "tags": online.get("tags") or [],
        "children": online.get("children") or [],
        "screenshots": online.get("screenshots") or [],
        "time_created": int(online.get("time_created") or 0),
        "time_updated": int(online.get("time_updated") or 0),
        "stats": stats,
        "item_type": online.get("item_type") or "mod",
        "consumer_app_id": int(online.get("consumer_app_id") or 0),
        "file_size": int(online.get("file_size") or 0),
        "status": online.get("status") or {},
        "maybe_inappropriate_sex": bool(online.get("maybe_inappropriate_sex") or False),
        "maybe_inappropriate_violence": bool(online.get("maybe_inappropriate_violence") or False),
        "revision_change_number": int(online.get("revision_change_number") or 0),
        "kv_tags": online.get("kv_tags") or [],
        "translations": online.get("translations") or {},
        "playtime_stats": online.get("playtime_stats"),
        "summary_last_sync_time": int(online.get("summary_last_sync_time") or 0),
        "detail_last_sync_time": int(online.get("detail_last_sync_time") or 0),
        "last_sync_time": int(online.get("last_sync_time") or 0),
    }


def _normalize_workshop_ids(workshop_ids: list[str]) -> list[str]:
    """规范化并保序去重 workshop_id，避免重复查询同一批缓存。"""
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for workshop_id in workshop_ids:
        normalized_id = normalize_cached_workshop_id(workshop_id)
        if not normalized_id or normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)
        normalized_ids.append(normalized_id)
    return normalized_ids


def _get_online_cache_map(workshop_ids: list[str]) -> dict[str, dict[str, Any]]:
    """按 workshop_id 批量读取在线缓存，避免逐条查询。"""
    normalized_ids = _normalize_workshop_ids(workshop_ids)
    if not normalized_ids: return {}

    rows = list(
        WorkshopOnlineCache.select(
            WorkshopOnlineCache.workshop_id,
            WorkshopOnlineCache.title,
            WorkshopOnlineCache.short_description,
            WorkshopOnlineCache.description,
            WorkshopOnlineCache.author_steam_id,
            WorkshopOnlineCache.preview_url,
            WorkshopOnlineCache.tags,
            WorkshopOnlineCache.children,
            WorkshopOnlineCache.screenshots,
            WorkshopOnlineCache.time_created,
            WorkshopOnlineCache.time_updated,
            WorkshopOnlineCache.stats,
            WorkshopOnlineCache.item_type,
            WorkshopOnlineCache.consumer_app_id,
            WorkshopOnlineCache.file_size,
            WorkshopOnlineCache.status,
            WorkshopOnlineCache.maybe_inappropriate_sex,
            WorkshopOnlineCache.maybe_inappropriate_violence,
            WorkshopOnlineCache.revision_change_number,
            WorkshopOnlineCache.kv_tags,
            WorkshopOnlineCache.translations,
            WorkshopOnlineCache.playtime_stats,
            WorkshopOnlineCache.summary_last_sync_time,
            WorkshopOnlineCache.detail_last_sync_time,
            WorkshopOnlineCache.last_sync_time,
        )
        .where(WorkshopOnlineCache.workshop_id.in_(normalized_ids))
        .dicts()
    )
    author_map = _get_author_cache_map([str(row.get("author_steam_id") or "") for row in rows])
    for row in rows:
        author_steam_id = str(row.get("author_steam_id") or "").strip()
        if author_steam_id and author_steam_id in author_map:
            row["author_profile"] = author_map[author_steam_id]
    return {str(row["workshop_id"]): row for row in rows}


def _merge_manifest_rows(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量为 manifest 行补齐在线缓存字段，统一返回结构。"""
    if not manifests: return []
    online_map = _get_online_cache_map([str(row.get("workshop_id") or "") for row in manifests])
    return [
        _merge_manifest_with_online(manifest, online_map.get(str(manifest.get("workshop_id") or "").strip()))
        for manifest in manifests
    ]


def _dedupe_text_terms(values: Any) -> list[str]:
    """把前端传来的逗号/换行分隔条件整理成稳定列表。"""
    if isinstance(values, str):
        raw_values = re.split(r"[,，;\n\r]+", values)
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    else:
        raw_values = []

    terms: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        term = str(value or "").strip()
        key = term.lower()
        if not term or key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def _combine_or(expressions: list[Any]):
    if not expressions: return None
    result = expressions[0]
    for expression in expressions[1:]:
        result = result | expression
    return result


def _combine_and(expressions: list[Any]):
    if not expressions: return None
    result = expressions[0]
    for expression in expressions[1:]:
        result = result & expression
    return result


def _field_contains_text(field: Any, value: str):
    return fn.LOWER(field).contains(str(value or "").strip().lower())


def _parse_cache_query_groups(query: str) -> list[list[str]]:
    """
    缓存搜索的轻量与/或语法：
    - 空格表示同时包含；
    - `|` 表示任一分组命中。
    """
    groups: list[list[str]] = []
    for group_text in re.split(r"\s*\|\s*", str(query or "").strip()):
        terms = [term for term in re.split(r"\s+", group_text.strip()) if term]
        if terms:
            groups.append(terms)
    return groups


def _build_cache_text_expression(query: str):
    groups = _parse_cache_query_groups(query)
    if not groups: return None

    search_fields = [
        WorkshopManifest.workshop_id,
        WorkshopManifest.package_id,
        WorkshopManifest.name,
        WorkshopManifest.author,
        WorkshopOnlineCache.title,
        WorkshopOnlineCache.short_description,
        WorkshopOnlineCache.author_steam_id,
    ]
    group_expressions = []
    for terms in groups:
        term_expressions = []
        for term in terms:
            term_expressions.append(_combine_or([_field_contains_text(field, term) for field in search_fields]))
        group_expression = _combine_and([expr for expr in term_expressions if expr is not None])
        if group_expression is not None:
            group_expressions.append(group_expression)
    return _combine_or(group_expressions)


def _build_cache_tag_expression(tags: list[str], *, match_all: bool, exclude: bool = False):
    tag_expressions = []
    for tag in tags:
        tag_expression = _combine_or(
            [
                _field_contains_text(WorkshopOnlineCache.tags, tag),
                _field_contains_text(WorkshopManifest.game_versions, tag),
            ]
        )
        if tag_expression is not None:
            tag_expressions.append(~tag_expression if exclude else tag_expression)
    return _combine_and(tag_expressions) if (match_all or exclude) else _combine_or(tag_expressions)


def _normalize_cache_search_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    filters = filters or {}
    if not isinstance(filters, dict):
        filters = {}
    return {
        "sort": str(filters.get("sort") or "").strip().lower(),
        "author": str(filters.get("author") or "").strip(),
        "required_tags": _dedupe_text_terms(filters.get("required_tags") or filters.get("requiredTags")),
        "excluded_tags": _dedupe_text_terms(filters.get("excluded_tags") or filters.get("excludedTags")),
        "match_all_tags": bool(filters.get("match_all_tags", filters.get("matchAllTags", True))),
        "required_dlc_appids": _dedupe_text_terms(filters.get("required_dlc_appids") or filters.get("requiredDlcAppids")),
        "child_publishedfileid": normalize_cached_workshop_id(
            filters.get("child_publishedfileid") or filters.get("childPublishedFileId") or ""
        ),
    }


def _build_cache_dlc_dependency_expression(appids: list[str]):
    package_ids = steam_appids_to_rimworld_package_ids(appids)
    if not package_ids:
        return None
    expressions = [
        _field_contains_text(WorkshopManifest.dependencies_mods.cast("text"), package_id)
        for package_id in package_ids
    ]
    return _combine_or(expressions)


def _build_cache_workshop_dependency_expression(workshop_id: str):
    """外置工坊库把普通模组依赖保存在 dependencies_mods，按工坊 ID 反查依赖者。"""
    normalized_id = normalize_cached_workshop_id(workshop_id)
    if not normalized_id:
        return None
    return WorkshopManifest.dependencies_mods.cast("text").contains(f'"{normalized_id}"')


def _apply_cache_search_order(search_query: Any, sort: str, has_query: bool):
    normalized_sort = sort or ("relevance" if has_query else "latest")
    if normalized_sort in {"latest", "updated", "update_time", "relevance"}:
        return search_query.order_by(fn.COALESCE(WorkshopOnlineCache.time_updated, 0).desc(), WorkshopManifest.workshop_id.desc())
    if normalized_sort in {"created", "published"}:
        return search_query.order_by(fn.COALESCE(WorkshopOnlineCache.time_created, 0).desc(), WorkshopManifest.workshop_id.desc())
    if normalized_sort in {"subscriptions", "popular"}:
        return search_query.order_by(fn.COALESCE(fn.json_extract(WorkshopOnlineCache.stats, "$.subscriptions"), 0).desc(), WorkshopManifest.workshop_id.desc())
    if normalized_sort in {"name", "title"}:
        return search_query.order_by(fn.LOWER(WorkshopManifest.name).asc(), WorkshopManifest.workshop_id.desc())
    if normalized_sort == "author":
        return search_query.order_by(fn.LOWER(WorkshopManifest.author).asc(), fn.LOWER(WorkshopManifest.name).asc())
    return search_query.order_by(WorkshopManifest.workshop_id.desc())


def _load_manifest_candidates_by_package_ids(normalized_package_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """
    批量读取 package_id -> manifest 候选列表，并顺手叠加在线缓存。

    这样后续选择逻辑只处理统一候选结构，查询代码无需分别访问多张表。
    """
    manifests = (
        WorkshopManifest.select(
            WorkshopManifest.workshop_id,
            WorkshopManifest.package_id,
            WorkshopManifest.name,
            WorkshopManifest.author,
            WorkshopManifest.game_versions,
        )
        .where(fn.LOWER(WorkshopManifest.package_id).in_(normalized_package_ids))
        .dicts()
    )

    manifest_map: dict[str, list[dict[str, Any]]] = {}
    for manifest in _merge_manifest_rows(list(manifests)):
        package_id = normalize_package_id(manifest.get("package_id"))
        if not package_id:
            continue
        manifest_map.setdefault(package_id, []).append(manifest)
    return manifest_map


def _load_replacement_candidates_by_package_ids(normalized_package_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    replacements = (
        ModReplacement.select(
            ModReplacement.old_package_id,
            ModReplacement.old_workshop_id,
            ModReplacement.old_name,
            ModReplacement.old_author,
            ModReplacement.new_workshop_id,
            ModReplacement.new_name,
            ModReplacement.new_package_id,
            ModReplacement.new_versions,
            ModReplacement.old_versions,
        )
        .where(fn.LOWER(ModReplacement.old_package_id).in_(normalized_package_ids))
        .dicts()
    )

    replacement_map: dict[str, list[dict[str, Any]]] = {}
    for replacement in replacements:
        package_id = normalize_package_id(replacement.get("old_package_id"))
        if package_id:
            replacement_map.setdefault(package_id, []).append(replacement)
    return replacement_map


def _load_workshop_meta_map(workshop_ids: list[str]) -> dict[str, dict[str, Any]]:
    """按 workshop_id 批量加载合并后的元数据，供 replacement 补全和详情查询复用。"""
    normalized_ids = _normalize_workshop_ids(workshop_ids)
    if not normalized_ids: return {}

    manifests = (
        WorkshopManifest.select(
            WorkshopManifest.workshop_id,
            WorkshopManifest.package_id,
            WorkshopManifest.name,
            WorkshopManifest.author,
            WorkshopManifest.game_versions,
        )
        .where(WorkshopManifest.workshop_id.in_(normalized_ids))
        .dicts()
    )
    merged_manifests = _merge_manifest_rows(list(manifests))
    return {str(manifest["workshop_id"]): manifest for manifest in merged_manifests}


def _build_workshop_summary_items(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 manifest 列表压缩为详情页同作者/反向依赖使用的轻量结构。"""
    return [
        {
            "workshop_id": str(item.get("workshop_id") or ""),
            "name": item.get("title") or item.get("name"),
            "title": item.get("title") or item.get("name"),
            "preview_url": item.get("preview_url"),
        }
        for item in _merge_manifest_rows(manifests)
    ]


def _build_workshop_related_result(items: list[dict[str, Any]], total: int, page: int, page_size: int, source: str) -> dict[str, Any]:
    """统一普通模式关联项响应，方便前端复用增强模式展示逻辑。"""
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
        "source": source,
    }


def _sort_workshop_related_items(manifests: list[dict[str, Any]], current_versions: list[str]) -> list[dict[str, Any]]:
    """详情页关联项优先展示当前版本可用的 Mod，再按名称稳定排序。"""
    version_set = {str(version or "").strip() for version in current_versions or [] if str(version or "").strip()}
    def sort_key(item: dict[str, Any]):
        item_versions = {str(version or "").strip() for version in (item.get("game_versions") or []) if str(version or "").strip()}
        version_miss = 0 if (version_set and item_versions.intersection(version_set)) else 1
        return (version_miss, str(item.get("name") or "").lower(), str(item.get("workshop_id") or ""))
    return sorted(manifests, key=sort_key)


def _limit_workshop_related_items(manifests: list[dict[str, Any]], current_versions: list[str], limit: int = 20) -> list[dict[str, Any]]:
    return _sort_workshop_related_items(manifests, current_versions)[:limit]


def _load_asset_source_candidates_by_package_ids(normalized_package_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """批量读取本地已安装资源，供安装来源推断使用。"""
    assets = (
        ModAsset.select(
            ModAsset.package_id,
            ModAsset.workshop_id,
            ModAsset.url,
            ModAsset.name,
            ModAsset.supported_versions,
            ModAsset.file_modify_time,
        )
        .where(fn.LOWER(ModAsset.package_id).in_(normalized_package_ids))
        .dicts()
    )

    asset_map: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        package_id = normalize_package_id(asset.get("package_id"))
        if not package_id:
            continue
        asset_map.setdefault(package_id, []).append(asset)
    return asset_map


def _build_replacement_install_source(
    package_id: str,
    replacement: dict[str, Any],
    replacement_meta_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_new_workshop_id = normalize_cached_workshop_id(replacement.get("new_workshop_id"))
    replacement_meta = replacement_meta_map.get(normalized_new_workshop_id, {}) if normalized_new_workshop_id else {}
    return build_install_source(
        {
            "package_id": replacement_meta.get("package_id")
            or replacement.get("new_package_id")
            or package_id,
            "workshop_id": normalized_new_workshop_id,
            "url": replacement_meta.get("url"),
            "name": replacement_meta.get("title")
            or replacement_meta.get("name")
            or replacement.get("new_name"),
            "supported_versions": replacement_meta.get("game_versions")
            or replacement.get("new_versions")
            or [],
        },
        fallback_package_id=package_id,
        source_origin="replacement",
        is_replacement=True,
    )


def _serialize_workshop_lookup(meta: dict[str, Any]) -> dict[str, Any]:
    """将内部合并结构转换成导入检查和 UI 期望的轻量返回格式。"""
    workshop_id = str(meta["workshop_id"])
    return {
        "workshop_id": workshop_id,
        "package_id": normalize_package_id(meta.get("package_id")),
        "name": meta.get("title") or meta.get("name") or "",
        "author": [meta.get("author")] if meta.get("author") else [],
        "preview_url": meta.get("preview_url"),
        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}",
    }


class WorkshopCacheDAO:
    """
    外置 Workshop 缓存数据库访问入口。

    该 DAO 负责组合文件快照、在线缓存和替代规则三类数据，
    并向调用方返回统一的 workshop 查询结果。
    """

    @staticmethod
    def get_workshop_id_by_package(package_id: str, current_game_version: str = ""):
        _require_database_dependencies()
        details = WorkshopCacheDAO.get_workshop_details_by_package_ids(
            [package_id],
            current_game_version=current_game_version,
        )
        detail = details.get(normalize_package_id(package_id))
        return (((detail or {}).get("display") or {}).get("selected") or {}).get("workshop_id")

    @staticmethod
    def get_replacement_suggestion(package_id: str, current_game_version: str):
        _require_database_dependencies()
        rule = ModReplacement.get_or_none(ModReplacement.old_package_id == normalize_package_id(package_id))
        if rule and score_version_support(current_game_version, rule.new_versions) > 0:
            return {
                "new_workshop_id": rule.new_workshop_id,
                "new_name": rule.new_name,
            }
        return None

    @staticmethod
    def get_manifest_by_workshop_id(workshop_id: str):
        """返回文件快照层记录，供依赖判断等稳定语义使用。"""
        _require_database_dependencies()
        normalized_id = normalize_cached_workshop_id(workshop_id)
        if not normalized_id: return None
        return WorkshopManifest.get_or_none(WorkshopManifest.workshop_id == normalized_id)

    @staticmethod
    def get_manifests_by_workshop_ids(workshop_ids: list[str]) -> dict[str, Any]:
        """批量返回文件快照层记录，供依赖判断和包名映射复用。"""
        _require_database_dependencies()
        normalized_ids = _normalize_workshop_ids(workshop_ids)
        if not normalized_ids: return {}
        manifests = (
            WorkshopManifest.select()
            .where(WorkshopManifest.workshop_id.in_(normalized_ids))
        )
        return {str(manifest.workshop_id): manifest for manifest in manifests}

    @staticmethod
    def get_merged_meta_by_workshop_id(workshop_id: str) -> dict[str, Any] | None:
        """返回按 workshop_id 合并后的元数据。"""
        _require_database_dependencies()
        normalized_id = normalize_cached_workshop_id(workshop_id)
        if not normalized_id: return None
        manifest = WorkshopManifest.get_or_none(WorkshopManifest.workshop_id == normalized_id)
        online = WorkshopOnlineCache.get_or_none(WorkshopOnlineCache.workshop_id == normalized_id)
        if not manifest and not online: return None
        return _merge_manifest_with_online(
            model_to_dict(manifest) if manifest else None,
            model_to_dict(online) if online else None,
        )

    @staticmethod
    def search_workshop(query: str, page: int = 1, page_size: int = 100, filters: dict[str, Any] | None = None):
        """
        在外置缓存库中分页搜索可用 Workshop 条目。

        搜索以 manifest 为主，因为 package_id 与依赖语义都来自文件快照；
        展示阶段再叠加在线缓存里的标题和封面。
        """
        _require_database_dependencies()
        normalized_query = str(query or "").strip().lower()
        normalized_filters = _normalize_cache_search_filters(filters)
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 100), 200))
        search_query = (
            WorkshopManifest.select(
                WorkshopManifest.workshop_id,
                WorkshopManifest.package_id,
                WorkshopManifest.name,
                WorkshopManifest.author,
                WorkshopManifest.game_versions,
            )
            .join(
                WorkshopOnlineCache,
                JOIN.LEFT_OUTER,
                on=(WorkshopManifest.workshop_id == WorkshopOnlineCache.workshop_id),
            )
            .where(
                (WorkshopManifest.package_id.is_null(False))
                & (WorkshopManifest.package_id != "")
            )
        )

        text_expression = _build_cache_text_expression(normalized_query)
        if text_expression is not None:
            search_query = search_query.where(text_expression)

        if normalized_filters["author"]:
            author_expression = _combine_or(
                [
                    _field_contains_text(WorkshopManifest.author, normalized_filters["author"]),
                    _field_contains_text(WorkshopOnlineCache.author_steam_id, normalized_filters["author"]),
                ]
            )
            if author_expression is not None:
                search_query = search_query.where(author_expression)

        required_tags = normalized_filters["required_tags"]
        if required_tags:
            required_tag_expression = _build_cache_tag_expression(required_tags, match_all=normalized_filters["match_all_tags"])
            if required_tag_expression is not None:
                search_query = search_query.where(required_tag_expression)

        excluded_tags = normalized_filters["excluded_tags"]
        if excluded_tags:
            excluded_tag_expression = _build_cache_tag_expression(excluded_tags, match_all=True, exclude=True)
            if excluded_tag_expression is not None:
                search_query = search_query.where(excluded_tag_expression)

        dlc_dependency_expression = _build_cache_dlc_dependency_expression(normalized_filters["required_dlc_appids"])
        if dlc_dependency_expression is not None:
            search_query = search_query.where(dlc_dependency_expression)

        workshop_dependency_expression = _build_cache_workshop_dependency_expression(normalized_filters["child_publishedfileid"])
        if workshop_dependency_expression is not None:
            search_query = search_query.where(workshop_dependency_expression)

        search_query = _apply_cache_search_order(search_query, normalized_filters["sort"], bool(normalized_query))

        total = search_query.count()
        manifests = list(search_query.paginate(page, page_size).dicts())
        items = _merge_manifest_rows(manifests)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "filters": normalized_filters,
        }

    @staticmethod
    def get_workshop_detail(workshop_id: str):
        """获取单个 workshop 的基础缓存详情。"""
        _require_database_dependencies()
        normalized_id = str(workshop_id)
        meta = WorkshopCacheDAO.get_merged_meta_by_workshop_id(normalized_id)
        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == normalized_id)
        return {
            "meta": meta,
            "replacement": model_to_dict(replacement) if replacement else None,
        }

    @staticmethod
    def get_workshop_dependencies(workshop_id: str):
        """普通模式：按外置库记录获取当前项依赖的父项详情，不触发 Steam Key 接口。"""
        _require_database_dependencies()
        normalized_id = normalize_cached_workshop_id(workshop_id)
        if not normalized_id:
            return _build_workshop_related_result([], 0, 1, 100, "cache_dependencies")
        meta = WorkshopCacheDAO.get_merged_meta_by_workshop_id(normalized_id)
        dependencies = meta.get("dependencies_mods") if meta else {}
        dependency_names = dependencies if isinstance(dependencies, dict) else {}
        dependency_ids = _normalize_workshop_ids(list(dependency_names.keys()))
        detail_map = _load_workshop_meta_map(dependency_ids)
        items = [
            detail_map.get(dep_id) or {
                "workshop_id": dep_id,
                "name": dependency_names.get(dep_id) or dep_id,
                "title": dependency_names.get(dep_id) or dep_id,
                "preview_url": None,
            }
            for dep_id in dependency_ids
            if dep_id != normalized_id
        ]
        return _build_workshop_related_result(items, len(items), 1, max(1, len(items) or 100), "cache_dependencies")

    @staticmethod
    def search_workshop_dependents(workshop_id: str, page: int = 1, page_size: int = 20):
        """普通模式：按外置库反查依赖当前项的生态关联项，不触发 Steam Key 接口。"""
        _require_database_dependencies()
        normalized_id = normalize_cached_workshop_id(workshop_id)
        if not normalized_id:
            return _build_workshop_related_result([], 0, 1, page_size, "cache_dependents")
        result = WorkshopCacheDAO.search_workshop(
            "",
            page=page,
            page_size=page_size,
            filters={"child_publishedfileid": normalized_id, "sort": "latest"},
        )
        result["source"] = "cache_dependents"
        result["has_more"] = int(result["page"]) * int(result["page_size"]) < int(result["total"])
        return result

    @staticmethod
    def get_workshop_same_author(workshop_id: str, page: int = 1, page_size: int = 20):
        """普通模式：按外置库作者名查找同作者作品，不触发 Steam Key 接口。"""
        _require_database_dependencies()
        normalized_id = normalize_cached_workshop_id(workshop_id)
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 200))
        if not normalized_id:
            return _build_workshop_related_result([], 0, page, page_size, "cache_same_author")
        meta = WorkshopCacheDAO.get_merged_meta_by_workshop_id(normalized_id)
        author = str((meta or {}).get("author") or "").strip()
        if not author:
            return _build_workshop_related_result([], 0, page, page_size, "cache_same_author")
        manifests = list(
            WorkshopManifest.select(
                WorkshopManifest.workshop_id,
                WorkshopManifest.name,
                WorkshopManifest.author,
                WorkshopManifest.game_versions,
            )
            .where(
                (WorkshopManifest.author == author)
                & (WorkshopManifest.workshop_id != normalized_id)
                & (WorkshopManifest.package_id.is_null(False))
                & (WorkshopManifest.package_id != "")
            )
            .dicts()
        )
        sorted_manifests = _sort_workshop_related_items(manifests, list((meta or {}).get("game_versions") or []))
        start = (page - 1) * page_size
        items = _build_workshop_summary_items(sorted_manifests[start:start + page_size])
        return _build_workshop_related_result(items, len(sorted_manifests), page, page_size, "cache_same_author")

    @staticmethod
    def get_workshop_detail_extended(workshop_id: str):
        """
        获取适合详情页展示的扩展缓存信息。

        除了当前条目本身，还会补充：
        - 同作者其他 Mod
        - 反向依赖该 Mod 的其他条目
        """
        _require_database_dependencies()
        normalized_id = str(workshop_id)
        meta = WorkshopCacheDAO.get_merged_meta_by_workshop_id(normalized_id)
        if not meta: return None

        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == normalized_id)
        same_author_mods = []
        author = meta.get("author")
        current_versions = list(meta.get("game_versions") or [])
        if author:
            manifests = list(
                WorkshopManifest.select(
                    WorkshopManifest.workshop_id,
                    WorkshopManifest.name,
                    WorkshopManifest.author,
                    WorkshopManifest.game_versions,
                )
                .where(
                    (WorkshopManifest.author == author)
                    & (WorkshopManifest.workshop_id != normalized_id)
                    & (WorkshopManifest.package_id.is_null(False))
                    & (WorkshopManifest.package_id != "")
                )
                .dicts()
            )
            same_author_mods = _build_workshop_summary_items(_limit_workshop_related_items(manifests, current_versions))

        dependents_manifests = list(
            WorkshopManifest.select(
                WorkshopManifest.workshop_id,
                WorkshopManifest.name,
                WorkshopManifest.game_versions,
            )
            .where(
                (WorkshopManifest.dependencies_mods.cast("text").contains(f'"{normalized_id}"'))
                & (WorkshopManifest.package_id.is_null(False))
                & (WorkshopManifest.package_id != "")
            )
            .dicts()
        )
        dependents_mods = _build_workshop_summary_items(_limit_workshop_related_items(dependents_manifests, current_versions))

        return {
            "meta": meta,
            "replacement_mod": model_to_dict(replacement) if replacement else None,
            "same_author_mods": same_author_mods,
            "dependents_mods": dependents_mods,
        }

    @staticmethod
    def get_workshop_details_by_package_ids(package_ids: list[str], current_game_version: str = ""):
        """
        批量获取 package_id 对应的离线缓存详情。

        返回结构保持三段式：
        - direct: 直接命中的原版候选
        - replacement: 替代规则候选
        - display: 供 UI 直接展示的已选结果
        """
        _require_database_dependencies()
        normalized_package_ids = normalize_package_ids(package_ids)
        if not normalized_package_ids: return {}

        meta_map = _load_manifest_candidates_by_package_ids(normalized_package_ids)
        replacement_map = _load_replacement_candidates_by_package_ids(normalized_package_ids)
        replacement_meta_map = _load_workshop_meta_map(
            [
                replacement.get("new_workshop_id", "")
                for replacements in replacement_map.values()
                for replacement in replacements
                if replacement.get("new_workshop_id")
            ]
        )

        result: dict[str, dict[str, Any]] = {}
        for package_id in normalized_package_ids:
            lookup = build_workshop_detail_lookup(
                package_id,
                meta_candidates=meta_map.get(package_id, []),
                replacement_candidates=replacement_map.get(package_id, []),
                replacement_meta_map=replacement_meta_map,
                current_game_version=current_game_version,
            )
            if (
                ((lookup.get("direct") or {}).get("selected"))
                or ((lookup.get("replacement") or {}).get("selected"))
                or ((lookup.get("display") or {}).get("selected"))
            ):
                result[package_id] = lookup
        return result

    @staticmethod
    def get_install_sources_by_package_ids(package_ids: list[str], current_game_version: str = ""):
        """
        批量返回 package_id 对应的原始安装来源与替代来源。

        这里不会把 replacement 混进 original，
        便于前端分别统计“原版来源”和“替代来源”。
        """
        _require_database_dependencies()
        normalized_package_ids = normalize_package_ids(package_ids)
        if not normalized_package_ids: return {}

        asset_map = _load_asset_source_candidates_by_package_ids(normalized_package_ids)
        meta_map = _load_manifest_candidates_by_package_ids(normalized_package_ids)
        replacement_map = _load_replacement_candidates_by_package_ids(normalized_package_ids)
        replacement_meta_map = _load_workshop_meta_map(
            [
                replacement.get("new_workshop_id", "")
                for replacements in replacement_map.values()
                for replacement in replacements
                if replacement.get("new_workshop_id")
            ]
        )

        result: dict[str, dict[str, Any]] = {}
        for package_id in normalized_package_ids:
            replacement_sources = dedupe_install_sources(
                [
                    _build_replacement_install_source(package_id, replacement, replacement_meta_map)
                    for replacement in replacement_map.get(package_id, [])
                ]
            )
            replacement_sources = [source for source in replacement_sources if source]
            replacement_sources.sort(
                key=lambda source: install_source_sort_key(current_game_version, source),
                reverse=True,
            )
            replacement_workshop_ids = {
                normalize_cached_workshop_id(source.get("workshop_id"))
                for source in replacement_sources
                if source.get("kind") == "workshop"
            }
            replacement_urls = {
                str(source.get("url") or "").strip()
                for source in replacement_sources
                if source.get("kind") == "url" and source.get("url")
            }

            original_sources = dedupe_install_sources(
                [
                    *[
                        {
                            "package_id": package_id,
                            "workshop_id": replacement.get("old_workshop_id"),
                            "name": replacement.get("old_name") or replacement.get("old_package_id") or package_id,
                            "supported_versions": replacement.get("old_versions") or [],
                            "source_origin": "replacement_old",
                        }
                        for replacement in replacement_map.get(package_id, [])
                        if replacement.get("old_workshop_id")
                    ],
                    *[
                        {
                            "package_id": package_id,
                            "workshop_id": asset.get("workshop_id"),
                            "url": asset.get("url"),
                            "name": asset.get("name"),
                            "supported_versions": asset.get("supported_versions") or [],
                            "source_origin": "asset",
                        }
                        for asset in asset_map.get(package_id, [])
                    ],
                    *[
                        {
                            "package_id": package_id,
                            "workshop_id": meta.get("workshop_id"),
                            "name": meta.get("title") or meta.get("name"),
                            "supported_versions": meta.get("game_versions") or [],
                            "source_origin": "meta",
                        }
                        for meta in meta_map.get(package_id, [])
                    ],
                ]
            )
            original_sources = [
                source
                for source in original_sources
                if not (
                    (
                        source.get("kind") == "workshop"
                        and normalize_cached_workshop_id(source.get("workshop_id")) in replacement_workshop_ids
                    )
                    or (
                        source.get("kind") == "url"
                        and str(source.get("url") or "").strip() in replacement_urls
                    )
                )
            ]
            original_sources.sort(
                key=lambda source: install_source_sort_key(current_game_version, source),
                reverse=True,
            )

            result[package_id] = {
                "package_id": package_id,
                "original_sources": original_sources,
                "replacement_sources": replacement_sources,
            }

        return result

    @staticmethod
    def get_workshop_details_by_workshop_ids(workshop_ids: list[str]):
        """批量按 workshop_id 读取缓存详情，主要用于幽灵项和导入补全。"""
        _require_database_dependencies()
        normalized_ids = _normalize_workshop_ids(workshop_ids)
        if not normalized_ids: return {}

        meta_map = _load_workshop_meta_map(normalized_ids)
        return {
            str(workshop_id): _serialize_workshop_lookup(meta)
            for workshop_id, meta in meta_map.items()
        }


# 兼容项目内以 ExtDAO 名称导入的调用点。
ExtDAO = WorkshopCacheDAO
