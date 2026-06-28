from __future__ import annotations

from typing import Any

from peewee import JOIN, fn
from playhouse.shortcuts import model_to_dict

from backend.database.models import ModAsset
from backend.database.models_ext import ModReplacement, WorkshopManifest, WorkshopOnlineCache
from backend.database.workshop_selection import (
    build_install_source,
    build_workshop_detail_lookup,
    dedupe_install_sources,
    install_source_sort_key,
    normalize_cached_workshop_id,
)
from backend.utils.tools import normalize_package_id, normalize_package_ids
from backend.utils.versioning import score_version_support


def _require_database_dependencies() -> None:
    """确保数据库相关依赖可用。"""
    if (
        model_to_dict is None
        or fn is None
        or WorkshopManifest is None
        or WorkshopOnlineCache is None
        or ModReplacement is None
        or ModAsset is None
    ):
        raise ModuleNotFoundError("dao_ext database dependencies are unavailable")


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
    return {
        "workshop_id": workshop_id,
        "package_id": manifest.get("package_id"),
        "name": manifest.get("name"),
        "title": online.get("title") or manifest.get("name"),
        "author": manifest.get("author"),
        "author_steam_id": online.get("author_steam_id"),
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
        "subscriptions": int(online.get("subscriptions") or 0),
        "favorited": int(online.get("favorited") or 0),
        "lifetime_subscriptions": int(online.get("lifetime_subscriptions") or 0),
        "lifetime_favorited": int(online.get("lifetime_favorited") or 0),
        "views": int(online.get("views") or 0),
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

    rows = (
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
            WorkshopOnlineCache.subscriptions,
            WorkshopOnlineCache.favorited,
            WorkshopOnlineCache.lifetime_subscriptions,
            WorkshopOnlineCache.lifetime_favorited,
            WorkshopOnlineCache.views,
            WorkshopOnlineCache.summary_last_sync_time,
            WorkshopOnlineCache.detail_last_sync_time,
            WorkshopOnlineCache.last_sync_time,
        )
        .where(WorkshopOnlineCache.workshop_id.in_(normalized_ids))
        .dicts()
    )
    return {str(row["workshop_id"]): row for row in rows}


def _merge_manifest_rows(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量为 manifest 行补齐在线缓存字段，统一返回结构。"""
    if not manifests: return []
    online_map = _get_online_cache_map([str(row.get("workshop_id") or "") for row in manifests])
    return [
        _merge_manifest_with_online(manifest, online_map.get(str(manifest.get("workshop_id") or "").strip()))
        for manifest in manifests
    ]


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
    def search_workshop(query: str, page: int = 1, page_size: int = 100):
        """
        在外置缓存库中分页搜索可用 Workshop 条目。

        搜索以 manifest 为主，因为 package_id 与依赖语义都来自文件快照；
        展示阶段再叠加在线缓存里的标题和封面。
        """
        _require_database_dependencies()
        normalized_query = str(query or "").strip().lower()
        search_query = (
            WorkshopManifest.select(
                WorkshopManifest.workshop_id,
                WorkshopManifest.package_id,
                WorkshopManifest.name,
                WorkshopManifest.author,
                WorkshopManifest.game_versions,
            )
            .where(
                (WorkshopManifest.package_id.is_null(False))
                & (WorkshopManifest.package_id != "")
            )
        )

        if normalized_query:
            search_query = search_query.where(
                (WorkshopManifest.workshop_id.contains(normalized_query))
                | (WorkshopManifest.package_id.contains(normalized_query))
                | (fn.LOWER(WorkshopManifest.name).contains(normalized_query))
            )
        else:
            # 排序必须发生在分页之前，否则只会把“当前页内”排成最新顺序。
            search_query = (
                search_query
                .join(
                    WorkshopOnlineCache,
                    JOIN.LEFT_OUTER,
                    on=(WorkshopManifest.workshop_id == WorkshopOnlineCache.workshop_id),
                )
                .order_by(
                    fn.COALESCE(WorkshopOnlineCache.time_updated, 0).desc(),
                    WorkshopManifest.workshop_id.desc(),
                )
            )

        total = search_query.count()
        manifests = list(search_query.paginate(page, page_size).dicts())
        items = _merge_manifest_rows(manifests)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
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
        if author:
            manifests = list(
                WorkshopManifest.select(
                    WorkshopManifest.workshop_id,
                    WorkshopManifest.name,
                    WorkshopManifest.author,
                )
                .where(
                    (WorkshopManifest.author == author)
                    & (WorkshopManifest.workshop_id != normalized_id)
                    & (WorkshopManifest.package_id.is_null(False))
                    & (WorkshopManifest.package_id != "")
                )
                .limit(20)
                .dicts()
            )
            same_author_mods = _build_workshop_summary_items(manifests)

        dependents_manifests = list(
            WorkshopManifest.select(
                WorkshopManifest.workshop_id,
                WorkshopManifest.name,
            )
            .where(
                (WorkshopManifest.dependencies_mods.cast("text").contains(f'"{normalized_id}"'))
                & (WorkshopManifest.package_id.is_null(False))
                & (WorkshopManifest.package_id != "")
            )
            .limit(20)
            .dicts()
        )
        dependents_mods = _build_workshop_summary_items(dependents_manifests)

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
