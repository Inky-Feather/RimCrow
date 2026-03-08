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
        """外置数据分页搜索 (仅查找 Mod，排除合集)"""
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
    def get_nexus_detail(workshop_id: str):
        """获取 Mod 的完整云端档案 (含详情、依赖、替代品)"""
        wid = str(workshop_id)
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == wid)
        replacement = ModReplacement.get_or_none(ModReplacement.old_workshop_id == wid)
        return {
            "meta": model_to_dict(meta) if meta else None,
            "replacement": model_to_dict(replacement) if replacement else None
        }
    
    @staticmethod
    def get_nexus_detail_extended(workshop_id: str):
        """获取 Mod 的完整云端档案及生态圈数据"""
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