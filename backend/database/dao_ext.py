# backend/database/dao_ext.py
try:
    from playhouse.shortcuts import model_to_dict
    from peewee import fn
    from backend.database.models_ext import WorkshopMeta, ModReplacement
except ModuleNotFoundError:
    model_to_dict = None
    fn = None
    WorkshopMeta = None
    ModReplacement = None
from backend.utils.tools import normalize_package_id, normalize_workshop_id
from backend.utils.versioning import score_version_support


def _require_database_dependencies() -> None:
    if model_to_dict is None or fn is None or WorkshopMeta is None or ModReplacement is None:
        raise ModuleNotFoundError("dao_ext database dependencies are unavailable")


def _candidate_sort_key(current_game_version: str, candidate: dict):
    return (
        score_version_support(current_game_version, candidate.get("game_versions")),
        int(candidate.get("time_updated") or 0),
        1 if candidate.get("author") else 0,
        candidate.get("workshop_id") or "",
    )


def _build_meta_candidate(meta: dict) -> dict | None:
    workshop_id = normalize_workshop_id(meta.get("workshop_id"), digits_only=True, min_length=7, max_length=20)
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


def _build_replacement_candidate(package_id: str, replacement: dict, replacement_meta: dict | None) -> dict | None:
    workshop_id = normalize_workshop_id(replacement.get("new_workshop_id"), digits_only=True, min_length=7, max_length=20)
    if not workshop_id:
        return None

    if replacement_meta:
        return {
            "workshop_id": workshop_id,
            "package_id": normalize_package_id(replacement_meta.get("package_id") or replacement.get("new_package_id") or package_id),
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


def select_best_workshop_detail_for_package(
    package_id: str,
    meta_candidates: list[dict] | None,
    replacement_candidates: list[dict] | None,
    replacement_meta_map: dict[str, dict] | None = None,
    current_game_version: str = "",
) -> dict | None:
    normalized_package_id = normalize_package_id(package_id)
    replacement_meta_map = replacement_meta_map or {}

    direct_pool: dict[str, dict] = {}
    for meta in meta_candidates or []:
        candidate = _build_meta_candidate(meta)
        if candidate:
            direct_pool[candidate["workshop_id"]] = candidate

    replacement_pool: dict[str, dict] = {}
    for replacement in replacement_candidates or []:
        replacement_meta = replacement_meta_map.get(
            normalize_workshop_id(replacement.get("new_workshop_id"), digits_only=True, min_length=7, max_length=20)
        )
        candidate = _build_replacement_candidate(normalized_package_id, replacement, replacement_meta)
        if candidate:
            replacement_pool[candidate["workshop_id"]] = candidate

    pool = list(replacement_pool.values()) if replacement_pool else list(direct_pool.values())
    if not pool:
        return None

    best = max(pool, key=lambda candidate: _candidate_sort_key(current_game_version, candidate))
    return {
        "package_id": best["package_id"] or normalized_package_id,
        "package_id_raw": best["package_id"] or normalized_package_id,
        "workshop_id": best["workshop_id"],
        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={best['workshop_id']}",
        "name": best["name"] or normalized_package_id,
        "author": [best["author"]] if best.get("author") else [],
        "preview_url": best.get("preview_url"),
        "is_replacement_derived": bool(best.get("is_replacement_derived")),
        "selection_reason": best.get("selection_reason"),
        "candidate_count": len(pool),
    }


class ExtDAO:
    @staticmethod
    def get_workshop_id_by_package(package_id: str, current_game_version: str = ""):
        """通过包名反查工坊 ID"""
        _require_database_dependencies()
        details = ExtDAO.get_workshop_details_by_package_ids([package_id], current_game_version=current_game_version)
        detail = details.get(normalize_package_id(package_id))
        return detail.get("workshop_id") if detail else None

    @staticmethod
    def get_replacement_suggestion(package_id: str, current_game_version: str):
        """获取替代建议"""
        _require_database_dependencies()
        rule = ModReplacement.get_or_none(ModReplacement.old_package_id == normalize_package_id(package_id))
        if rule and score_version_support(current_game_version, rule.new_versions) > 0:
            return {
                "new_workshop_id": rule.new_workshop_id,
                "new_name": rule.new_name
            }
        return None
    
    @staticmethod
    def search_workshop(query: str, page: int = 1, page_size: int = 100):
        """外置数据分页搜索 (仅查找 Mod，排除合集)"""
        _require_database_dependencies()
        # 排除合集：合集通常没有 package_id，或者我们可以靠长度/内容判断
        q = WorkshopMeta.select(
            WorkshopMeta.workshop_id,
            WorkshopMeta.package_id,
            WorkshopMeta.name,
            WorkshopMeta.author,
            WorkshopMeta.preview_url,
            WorkshopMeta.time_updated
        ).where(
            (WorkshopMeta.package_id.is_null(False)) & 
            (WorkshopMeta.package_id != '')
        )

        if query:
            q = q.where(
                (WorkshopMeta.workshop_id.contains(query)) |
                (WorkshopMeta.package_id.contains(query.lower())) |
                (fn.LOWER(WorkshopMeta.name).contains(query.lower()))
            )
            
        # 排序：有搜索词时按匹配度（SQLite 默认顺序），无搜索词时按更新时间或名字
        if not query:
            q = q.order_by(WorkshopMeta.time_updated.desc())

        total = q.count()
        items = list(q.paginate(page, page_size).dicts())
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    
    
    @staticmethod
    def get_workshop_detail(workshop_id: str):
        """获取 Mod 的完整云端档案 (含详情、依赖、替代品)"""
        _require_database_dependencies()
        wid = str(workshop_id)
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == wid)
        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == wid)
        return {
            "meta": model_to_dict(meta) if meta else None,
            "replacement": model_to_dict(replacement) if replacement else None
        }
    
    @staticmethod
    def get_workshop_detail_extended(workshop_id: str):
        """获取 Mod 的完整云端档案及生态圈数据"""
        _require_database_dependencies()
        wid = str(workshop_id)
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == wid)
        if not meta: return None
        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == wid)
        # 1. 查找同作者的其他模组 (排除当前项，最多取 20 个)
        same_author = []
        if meta.author:
            author_query = WorkshopMeta.select(
                WorkshopMeta.workshop_id, WorkshopMeta.name, WorkshopMeta.preview_url
            ).where(
                (WorkshopMeta.author == meta.author) & 
                (WorkshopMeta.workshop_id != wid) &
                (WorkshopMeta.package_id.is_null(False)) & 
                (WorkshopMeta.package_id != '')
            ).limit(20).dicts()
            same_author = list(author_query)
        # 2. 查找反向依赖 (以当前 Mod 为前置的模组)
        # 因为 dependencies_mods 是 JSON 字符串 {"2891845502": "Name"}
        # 使用 contains 进行快速文本匹配
        dependents = []
        dep_query = WorkshopMeta.select(
            WorkshopMeta.workshop_id, WorkshopMeta.name, WorkshopMeta.preview_url
        ).where(
            # 强转为 text 绕过自定义字段的 db_value 序列化，防止双引号转义为`\\"`
            (WorkshopMeta.dependencies_mods.cast('text').contains(f'"{wid}"')) &
            (WorkshopMeta.package_id.is_null(False)) & 
            (WorkshopMeta.package_id != '')
        ).limit(20).dicts()
        dependents = list(dep_query)
        return {
            "meta": model_to_dict(meta),
            "replacement_mod": model_to_dict(replacement) if replacement else None,
            "same_author_mods": same_author,
            "dependents_mods": dependents
        }

    @staticmethod
    def get_workshop_details_by_package_ids(package_ids: list[str], current_game_version: str = ""):
        """批量获取包名对应的云端缓存信息（无网络请求，专门用于填充前端幽灵项）"""
        _require_database_dependencies()
        if not package_ids: return {}
        lower_ids = [normalize_package_id(pid) for pid in package_ids]
        
        # 1. 查询基础信息
        metas = WorkshopMeta.select(
            WorkshopMeta.workshop_id, 
            WorkshopMeta.package_id,
            WorkshopMeta.name,
            WorkshopMeta.title,
            WorkshopMeta.author,
            WorkshopMeta.preview_url,
            WorkshopMeta.time_updated,
            WorkshopMeta.game_versions,
        ).where(fn.LOWER(WorkshopMeta.package_id).in_(lower_ids)).dicts()
        
        meta_dict: dict[str, list[dict]] = {}
        for meta in metas:
            if not meta.get('package_id'):
                continue
            meta_dict.setdefault(normalize_package_id(meta['package_id']), []).append(meta)
        
        # 2. 查询替代版本 (如果有替代，获取替代信息)
        replacements = ModReplacement.select(
            ModReplacement.old_package_id,
            ModReplacement.new_workshop_id,
            ModReplacement.new_name,
            ModReplacement.new_package_id,
            ModReplacement.new_versions,
        ).where(fn.LOWER(ModReplacement.old_package_id).in_(lower_ids)).dicts()
        
        rep_dict: dict[str, list[dict]] = {}
        for replacement in replacements:
            if not replacement.get('old_package_id'):
                continue
            rep_dict.setdefault(normalize_package_id(replacement['old_package_id']), []).append(replacement)
        
        # 3. 如果有替代，尝试读取替代版本的 WorkshopMeta 来覆盖信息
        new_wids = [r['new_workshop_id'] for r in replacements if r.get('new_workshop_id')]
        rep_metas = {}
        if new_wids:
            rep_metas_query = WorkshopMeta.select(
                WorkshopMeta.workshop_id,
                WorkshopMeta.package_id,
                WorkshopMeta.name,
                WorkshopMeta.title,
                WorkshopMeta.author,
                WorkshopMeta.preview_url,
                WorkshopMeta.time_updated,
                WorkshopMeta.game_versions,
            ).where(WorkshopMeta.workshop_id.in_(new_wids)).dicts()
            rep_metas = { m['workshop_id']: m for m in rep_metas_query }
            
        result = {}
        for pid in lower_ids:
            selected = select_best_workshop_detail_for_package(
                pid,
                meta_candidates=meta_dict.get(pid, []),
                replacement_candidates=rep_dict.get(pid, []),
                replacement_meta_map=rep_metas,
                current_game_version=current_game_version,
            )
            if selected:
                result[pid] = selected
        
                
        return result

    @staticmethod
    def get_workshop_details_by_workshop_ids(workshop_ids: list[str]):
        """
        批量获取 workshop id 对应的缓存信息。

        主要用于“纯 workshop id 导入”这种没有 package_id 的场景，
        尽量反查出 package_id、名称和封面，方便前端展示。
        """
        _require_database_dependencies()
        if not workshop_ids:
            return {}
        normalized_ids = [normalize_workshop_id(wid, digits_only=True, min_length=7, max_length=20) for wid in workshop_ids]
        normalized_ids = [wid for wid in normalized_ids if wid]
        if not normalized_ids:
            return {}

        metas = (
            WorkshopMeta
            .select(
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
        return {
            str(meta["workshop_id"]): {
                "workshop_id": str(meta["workshop_id"]),
                "package_id": normalize_package_id(meta.get("package_id")),
                "name": meta.get("title") or meta.get("name") or "",
                "author": [meta.get("author")] if meta.get("author") else [],
                "preview_url": meta.get("preview_url"),
                "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={meta['workshop_id']}",
            }
            for meta in metas
        }

