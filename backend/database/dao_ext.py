from __future__ import annotations
from typing import Any

from peewee import fn
from playhouse.shortcuts import model_to_dict

from backend.database.models_ext import ModReplacement, WorkshopMeta
from backend.database.workshop_selection import normalize_cached_workshop_id, select_best_workshop_detail_for_package
from backend.utils.tools import normalize_package_id, normalize_package_ids
from backend.utils.versioning import score_version_support


def _require_database_dependencies() -> None:
    """确保数据库相关依赖可用。"""
    if model_to_dict is None or fn is None or WorkshopMeta is None or ModReplacement is None:
        raise ModuleNotFoundError("dao_ext database dependencies are unavailable")


def _load_meta_candidates_by_package_ids(normalized_package_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """批量读取 package_id -> WorkshopMeta 候选列表。"""
    metas = (
        WorkshopMeta.select(
            WorkshopMeta.workshop_id,
            WorkshopMeta.package_id,
            WorkshopMeta.name,
            WorkshopMeta.title,
            WorkshopMeta.author,
            WorkshopMeta.preview_url,
            WorkshopMeta.time_updated,
            WorkshopMeta.game_versions,
        )
        .where(fn.LOWER(WorkshopMeta.package_id).in_(normalized_package_ids))
        .dicts()
    )

    meta_map: dict[str, list[dict[str, Any]]] = {}
    for meta in metas:
        package_id = normalize_package_id(meta.get("package_id"))
        if package_id:
            meta_map.setdefault(package_id, []).append(meta)
    return meta_map


def _load_replacement_candidates_by_package_ids(normalized_package_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """批量读取 package_id -> replacement 规则候选列表。"""
    replacements = (
        ModReplacement.select(
            ModReplacement.old_package_id,
            ModReplacement.new_workshop_id,
            ModReplacement.new_name,
            ModReplacement.new_package_id,
            ModReplacement.new_versions,
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
    """按 workshop_id 批量加载 WorkshopMeta 记录，便于 replacement 候选补全信息。"""
    normalized_ids = [normalize_cached_workshop_id(workshop_id) for workshop_id in workshop_ids]
    normalized_ids = [workshop_id for workshop_id in normalized_ids if workshop_id]
    if not normalized_ids:
        return {}

    metas = (
        WorkshopMeta.select(
            WorkshopMeta.workshop_id,
            WorkshopMeta.package_id,
            WorkshopMeta.name,
            WorkshopMeta.title,
            WorkshopMeta.author,
            WorkshopMeta.preview_url,
            WorkshopMeta.time_updated,
            WorkshopMeta.game_versions,
        )
        .where(WorkshopMeta.workshop_id.in_(normalized_ids))
        .dicts()
    )
    return {meta["workshop_id"]: meta for meta in metas}


def _serialize_workshop_lookup(meta: dict[str, Any]) -> dict[str, Any]:
    """将 workshop_id 直查结果统一为导入检查和 UI 期望的结构。"""
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

    这里的职责只包括：
    - 查询 WorkshopMeta / ModReplacement
    - 组装离线缓存接口需要的返回结构
    - 调用纯选择策略函数
    """

    @staticmethod
    def get_workshop_id_by_package(package_id: str, current_game_version: str = ""):
        """通过包名反查最合适的 workshop_id。"""
        _require_database_dependencies()
        details = WorkshopCacheDAO.get_workshop_details_by_package_ids(
            [package_id],
            current_game_version=current_game_version,
        )
        detail = details.get(normalize_package_id(package_id))
        return detail.get("workshop_id") if detail else None

    @staticmethod
    def get_replacement_suggestion(package_id: str, current_game_version: str):
        """根据替代规则返回当前游戏版本可用的 replacement 建议。"""
        _require_database_dependencies()
        rule = ModReplacement.get_or_none(ModReplacement.old_package_id == normalize_package_id(package_id))
        if rule and score_version_support(current_game_version, rule.new_versions) > 0:
            return {
                "new_workshop_id": rule.new_workshop_id,
                "new_name": rule.new_name,
            }
        return None

    @staticmethod
    def search_workshop(query: str, page: int = 1, page_size: int = 100):
        """
        在外置缓存库中分页搜索可用 Workshop 条目。

        当前实现只返回带 package_id 的条目，刻意过滤掉合集，
        因为这个接口主要服务于 Mod 查询，而不是合集浏览。
        """
        _require_database_dependencies()
        normalized_query = str(query or "").strip().lower()
        search_query = (
            WorkshopMeta.select(
                WorkshopMeta.workshop_id,
                WorkshopMeta.package_id,
                WorkshopMeta.name,
                WorkshopMeta.author,
                WorkshopMeta.preview_url,
                WorkshopMeta.time_updated,
            )
            .where(
                (WorkshopMeta.package_id.is_null(False))
                & (WorkshopMeta.package_id != "")
            )
        )

        if normalized_query:
            search_query = search_query.where(
                (WorkshopMeta.workshop_id.contains(normalized_query))
                | (WorkshopMeta.package_id.contains(normalized_query))
                | (fn.LOWER(WorkshopMeta.name).contains(normalized_query))
            )
        else:
            search_query = search_query.order_by(WorkshopMeta.time_updated.desc())

        total = search_query.count()
        items = list(search_query.paginate(page, page_size).dicts())
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def get_workshop_detail(workshop_id: str):
        """
        获取单个 workshop 的基础缓存详情。

        该方法当前在仓库内没有直接调用，这一轮先保留，用于兼容潜在外部调用。
        """
        _require_database_dependencies()
        normalized_id = str(workshop_id)
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == normalized_id)
        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == normalized_id)
        return {
            "meta": model_to_dict(meta) if meta else None,
            "replacement": model_to_dict(replacement) if replacement else None,
        }

    @staticmethod
    def get_workshop_detail_extended(workshop_id: str):
        """
        获取更适合详情页展示的扩展缓存信息。

        除了当前条目本身，还会补充：
        - 同作者其他 Mod
        - 反向依赖该 Mod 的其他条目
        """
        _require_database_dependencies()
        normalized_id = str(workshop_id)
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == normalized_id)
        if not meta:
            return None

        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == normalized_id)
        same_author_mods = []
        if meta.author:
            same_author_mods = list(
                WorkshopMeta.select(
                    WorkshopMeta.workshop_id,
                    WorkshopMeta.name,
                    WorkshopMeta.preview_url,
                )
                .where(
                    (WorkshopMeta.author == meta.author)
                    & (WorkshopMeta.workshop_id != normalized_id)
                    & (WorkshopMeta.package_id.is_null(False))
                    & (WorkshopMeta.package_id != "")
                )
                .limit(20)
                .dicts()
            )

        dependents_mods = list(
            WorkshopMeta.select(
                WorkshopMeta.workshop_id,
                WorkshopMeta.name,
                WorkshopMeta.preview_url,
            )
            .where(
                (WorkshopMeta.dependencies_mods.cast("text").contains(f'"{normalized_id}"'))
                & (WorkshopMeta.package_id.is_null(False))
                & (WorkshopMeta.package_id != "")
            )
            .limit(20)
            .dicts()
        )

        return {
            "meta": model_to_dict(meta),
            "replacement_mod": model_to_dict(replacement) if replacement else None,
            "same_author_mods": same_author_mods,
            "dependents_mods": dependents_mods,
        }

    @staticmethod
    def get_workshop_details_by_package_ids(package_ids: list[str], current_game_version: str = ""):
        """
        批量获取 package_id 对应的离线缓存详情。

        这是前端“幽灵项补全”和导入检查会大量调用的接口，因此这里优先选择
        批量查询后内存仲裁，而不是对每个 package_id 单独查一遍数据库。
        """
        _require_database_dependencies()
        normalized_package_ids = normalize_package_ids(package_ids)
        if not normalized_package_ids:
            return {}

        meta_map = _load_meta_candidates_by_package_ids(normalized_package_ids)
        replacement_map = _load_replacement_candidates_by_package_ids(normalized_package_ids)
        replacement_meta_map = _load_workshop_meta_map(
            [
                replacement.get("new_workshop_id","")
                for replacements in replacement_map.values()
                for replacement in replacements
                if replacement.get("new_workshop_id")
            ]
        )

        result: dict[str, dict[str, Any]] = {}
        for package_id in normalized_package_ids:
            selected = select_best_workshop_detail_for_package(
                package_id,
                meta_candidates=meta_map.get(package_id, []),
                replacement_candidates=replacement_map.get(package_id, []),
                replacement_meta_map=replacement_meta_map,
                current_game_version=current_game_version,
            )
            if selected:
                result[package_id] = selected
        return result

    @staticmethod
    def get_workshop_details_by_workshop_ids(workshop_ids: list[str]):
        """
        批量按 workshop_id 读取缓存详情。

        主要用于“只有 workshop_id、没有 package_id”的导入场景，
        尽量补出包名、名称和封面，便于前端展示。
        """
        _require_database_dependencies()
        normalized_ids = [normalize_cached_workshop_id(workshop_id) for workshop_id in workshop_ids]
        normalized_ids = [workshop_id for workshop_id in normalized_ids if workshop_id]
        if not normalized_ids:
            return {}

        metas = (
            WorkshopMeta.select(
                WorkshopMeta.workshop_id,
                WorkshopMeta.package_id,
                WorkshopMeta.name,
                WorkshopMeta.title,
                WorkshopMeta.author,
                WorkshopMeta.preview_url,
            )
            .where(WorkshopMeta.workshop_id.in_(normalized_ids))
            .dicts()
        )
        return {str(meta["workshop_id"]): _serialize_workshop_lookup(meta) for meta in metas}


# 兼容现有调用方：项目内部仍然使用 ExtDAO 名称。
ExtDAO = WorkshopCacheDAO
