# backend/managers/mgr_workshop_db.py
import json
import gzip
import os
from pathlib import Path
from peewee import chunked
from dateutil import parser

from backend.utils.logger import logger
from backend.settings import settings
from backend.database.models_ext import ext_db, WorkshopMeta, ModReplacement, init_ext_db
from backend.database.models import SystemInfo, db as main_db

class WorkshopDBManager:
    def __init__(self):
        # 启动时连接缓存库
        init_ext_db()
        self.load_all_cache()
        
    def load_all_cache(self):
        """加载所有缓存"""
        self.rebuild_workshop_cache()
        self.rebuild_instead_cache()
        

    def rebuild_workshop_cache(self):
        """将 40MB 的 steamDB.json 灌入 SQLite，然后抛弃内存占用"""
        path = Path(settings.config.community_workshop_db_path)
        if not path.exists(): return False
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            version = str(data.get("version", "0"))
            raw_db = data.get("database", {})
            batch =[]
            for wid, info in raw_db.items():
                if wid == "294100": continue # 跳过游戏本体
                # 提取依赖项，压缩结构：{"2891845502": "Alpha Genes"}
                deps = {}
                for dep_id, dep_info in info.get("dependencies", {}).items():
                    deps[dep_id] = dep_info[0] if isinstance(dep_info, list) and dep_info else "Unknown"
                batch.append({
                    "workshop_id": wid,
                    "package_id": info.get("packageId", "").lower(),
                    "name": info.get("name", ""),
                    "author": info.get("authors", ""),
                    "game_versions": info.get("gameVersions",[]),
                    "dependencies_mods": deps
                })
            # 获取 user_data_list 中出现过的所有键，取交集，确保只更新传入的字段
            input_keys = set().union(*(d.keys() for d in batch))
            update_fields = [
                field for field in WorkshopMeta._meta.sorted_fields  # type: ignore
                if field.name in input_keys and field.name != "workshop_id"
            ]
            # 开启事务，批量插入（几秒钟即可完成几万条数据的写入）
            with ext_db.atomic():
                # WorkshopMeta.delete().execute() # 清空旧数据
                for chunk in chunked(batch, 500):
                    WorkshopMeta.insert_many(chunk).on_conflict(
                        conflict_target=[WorkshopMeta.workshop_id],
                        preserve=update_fields,
                    ).execute()
            # 记录版本号到主数据库
            SystemInfo.insert(key='steamdb_version', value=version).on_conflict_replace().execute()
            logger.info(f"SteamDB 缓存重建完成！总记录数: {len(batch)}")
            # 可选：转换完成后直接删除 JSON 文件节省用户硬盘空间
            # os.remove(path) 
            return True
        except Exception as e:
            # import traceback
            # traceback.print_exc()
            logger.error(f"SteamDB 重建失败: {e}", exc_info=True)
            return False

    def rebuild_instead_cache(self):
        """将 replacements.json 灌入 SQLite"""
        path = Path(settings.config.community_instead_db_path)
        # 支持自动寻找 .gz 文件后缀
        if not path.exists() and path.with_suffix(path.suffix + '.gz').exists():
            path = path.with_suffix(path.suffix + '.gz')
        if not path.exists(): return False
        try:
            if str(path).endswith(".gz"):
                with gzip.open(path, 'rt', encoding='utf-8-sig') as f:
                    content = json.load(f)
            else:
                with open(path, 'r', encoding='utf-8-sig') as f:
                    content = json.load(f)
                    
            version = str(content.get("version", "0"))
            rules = content.get("rules", [])
            
            batch =[]
            for r in rules:
                batch.append({
                    "old_workshop_id": r.get("oldWorkshopId"),
                    "old_package_id": str(r.get("oldPackageId", "")).lower(),
                    "new_workshop_id": r.get("newWorkshopId"),
                    "new_package_id": str(r.get("newPackageId", "")).lower(),
                    "new_name": r.get("newName", ""),
                    "old_versions": r.get("oldVersions",[]),
                    "new_versions": r.get("newVersions",[])
                })
                
            with ext_db.atomic():
                ModReplacement.delete().execute()
                for chunk in chunked(batch, 500):
                    ModReplacement.insert_many(chunk).execute()
                    
            SystemInfo.insert(key='instead_version', value=version).on_conflict_replace().execute()
            logger.info(f"替代规则库重建完成！总记录数: {len(batch)}")
            return True
        except Exception as e:
            logger.error(f"替代规则库重建失败: {e}")
            return False

    # =============== 极速 O(1) 查询接口 ===============
    
    def check_replacement(self, package_id: str, game_version: str):
        """替代方案极速检测"""
        rule = ModReplacement.get_or_none(ModReplacement.old_package_id == package_id.lower())
        if rule and game_version in rule.new_versions:
            return {
                "type": "instead",
                "new_id": rule.new_workshop_id,
                "new_name": rule.new_name,
                "message": f"发现接力版本：推荐使用 {rule.new_name} 替代当前模组。"
            }
        return None

    def get_missing_dependencies(self, workshop_id: str, local_installed_package_ids: set):
        """一键查找缺失的前置依赖"""
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == str(workshop_id))
        if not meta or not meta.dependencies_mods:
            return []
            
        missing =[]
        for dep_wid, dep_name in meta.dependencies_mods.items():
            # 反查依赖项的包名
            dep_meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == dep_wid)
            if dep_meta and dep_meta.package_id not in local_installed_package_ids:
                missing.append({"workshop_id": dep_wid, "name": dep_name})
                
        return missing
    
    