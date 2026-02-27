# backend/database/dao_ext.py
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