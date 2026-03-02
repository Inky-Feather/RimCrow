# backend/database/dao_ext.py
from playhouse.shortcuts import model_to_dict
from peewee import JOIN, fn
from backend.database.models_ext import WorkshopMeta, ModReplacement
from backend.utils.logger import logger

class ExtDAO:
    @staticmethod
    def get_workshop_id_by_package(package_id: str):
        """通过包名反查工坊 ID"""
        if not package_id: return None
        meta = WorkshopMeta.get_or_none(WorkshopMeta.package_id == package_id.lower())
        return meta.workshop_id if meta else None

    @staticmethod
    def get_replacement_suggestion(package_id: str, current_game_version: str):
        """获取替代建议"""
        rule = ModReplacement.get_or_none(ModReplacement.old_package_id == package_id.lower())
        if rule and current_game_version in rule.new_versions:
            return {
                "new_workshop_id": rule.new_workshop_id,
                "new_name": rule.new_name
            }
        return None
    
    @staticmethod
    def search_nexus(query: str, page: int = 1, page_size: int = 100):
        """外置数据分页搜索"""
        q = WorkshopMeta.select(
            WorkshopMeta.workshop_id,
            WorkshopMeta.package_id,
            WorkshopMeta.name,
            WorkshopMeta.author,
            WorkshopMeta.preview_url # 如果有缓存就直接带出去
        )
        if query:
            # 忽略大小写模糊搜索 ID, 包名, 名字
            q = q.where(
                (WorkshopMeta.workshop_id.contains(query)) |
                (WorkshopMeta.package_id.contains(query.lower())) |
                (fn.LOWER(WorkshopMeta.name).contains(query.lower()))
            )
        # 分页
        total = q.count()
        items = list(q.paginate(page, page_size).dicts())
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    
    
    @staticmethod
    def get_nexus_detail(workshop_id: str):
        """获取 Mod 的完整云端档案 (含详情、依赖、替代品)"""
        wid = str(workshop_id)
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == wid)
        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == wid)

        return {
            "meta": model_to_dict(meta) if meta else None,
            "replacement": model_to_dict(replacement) if replacement else None
        }