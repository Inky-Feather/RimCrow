import json
import gzip
import os
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Optional

from dateutil import parser

from backend.utils.logger import logger
from backend.settings import settings

class WorkshopDBManager:
    """
    社区数据库管理器
    职责：
    1. 管理 Steam Workshop 元数据 (ID, Name, Author, Dependencies)
    2. 管理模组替换建议 (Use This Instead)
    3. 为 mgr_mod_update.py 提供下载源信息和依赖树查询
    """

    def __init__(self):
        # --- 数据存储 ---
        # 结构: { "steam_id_str": { ...data... } }
        self.workshop_db: Dict[str, Dict[str, Any]] = {}
        
        # 索引: { "package_id_lower": ["steam_id_1", "steam_id_2"] }
        # 一个 PackageID 可能对应多个 SteamID (分叉版本)，所以用 List
        self.pkg_id_index: Dict[str, List[str]] = defaultdict(list)

        # 结构: [ { "oldWorkshopId":..., "newWorkshopId":... }, ... ]
        self.instead_db: List[Dict[str, Any]] = []
        
        # 索引: 为了快速查找，建立 (key_type, value) -> Rule 的映射
        # key 可以是 oldWorkshopId 或 oldPackageId
        self.instead_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        # 元数据版本信息
        self.db_versions = {
            "workshop": 0,
            "instead": 0
        }

        # 初始化加载
        self.load_all()

    def load_all(self):
        """加载所有外部数据库文件"""
        self._load_workshop_db()
        self._load_instead_db()
        logger.info(f"WorkshopDB loaded. Entries: {len(self.workshop_db)}, InsteadDB: {len(self.instead_db)}")

    # =========================================================================
    # 1. 加载逻辑 (Loader Logic)
    # =========================================================================

    def _load_workshop_db(self):
        """加载 Workshop DB (包含 Workshop 详情)"""
        path = Path(settings.config.community_workshop_db_path)
        if not path.exists():
            logger.warning(f"Workshop DB not found at {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 获取时间戳转为毫秒戳
            self.db_versions["workshop"] = int(data.get("version",0))*1000
            raw_db = data.get("database", {})
            
            # 清空旧数据
            self.workshop_db.clear()
            self.pkg_id_index.clear()

            # 构建索引
            for steam_id, info in raw_db.items():
                self.workshop_db[steam_id] = info
                
                # 建立 PackageID -> SteamID 的反向索引
                # 注意：数据源中的 packageId 可能有大小写差异，统一转小写存储索引
                if "packageId" in info:
                    pid_lower = info["packageId"].lower()
                    self.pkg_id_index[pid_lower].append(steam_id)
                
        except Exception as e:
            logger.error(f"Failed to load community rules DB: {e}")

    def _load_instead_db(self):
        """加载 Instead DB (支持 .json 和 .json.gz)"""
        path = Path(settings.config.community_instead_db_path)
        if not path.exists():
            # 尝试找找有没有加了 .gz 后缀的文件 (如果配置路径没带.gz但文件是.gz)
            path_gz = path.with_suffix(path.suffix + ".gz")
            if path_gz.exists():
                path = path_gz
            else:
                logger.warning(f"Instead DB not found at {path}")
                return

        try:
            content = None
            # 智能判断是否需要解压
            if str(path).endswith(".gz"):
                # 关键：使用 utf-8-sig 编码处理BOM
                with gzip.open(path, 'rt', encoding='utf-8-sig') as f:
                    content = json.load(f)
            else:
                # 关键：使用 utf-8-sig 编码处理BOM
                with open(path, 'r', encoding='utf-8-sig') as f:
                    content = json.load(f)
                    
            if not content:
                logger.warning("Instead DB content is empty")
                return
            
            time_str = content.get("version","0")
            # 将 2024-09-04 07:26:36 格式转为毫秒戳
            time_stamp = int(parser.parse(time_str).timestamp() * 1000)
            self.db_versions["instead"] = time_stamp
            self.instead_db = content.get("rules", [])
            # 清空索引
            self.instead_index.clear()
            # 构建快速查找索引
            for rule in self.instead_db:
                # 索引1: 通过 WorkshopID 查找
                if "oldWorkshopId" in rule and rule["oldWorkshopId"]:
                    key = f"wid:{rule['oldWorkshopId']}"
                    # 使用setdefault初始化空列表，避免KeyError
                    self.instead_index.setdefault(key, []).append(rule)
                # 索引2: 通过 PackageID 查找 (转小写)
                if "oldPackageId" in rule and rule["oldPackageId"]:
                    pid_lower = rule["oldPackageId"].lower()
                    key = f"pid:{pid_lower}"
                    # 使用setdefault初始化空列表，避免KeyError
                    self.instead_index.setdefault(key, []).append(rule)

        except Exception as e:
            logger.error(f"Failed to load replacements DB: {e}")

    # =========================================================================
    # 2. 查询接口 (Query Interface)
    # =========================================================================

    def get_mod_info_by_id(self, steam_id: str) -> Optional[Dict[str, Any]]:
        """通过 Steam ID 获取模组详情"""
        return self.workshop_db.get(str(steam_id))

    def get_steam_ids_by_package_id(self, package_id: str) -> List[str]:
        """通过 Package ID 获取可能的 Steam ID 列表 (可能有多个)"""
        return self.pkg_id_index.get(package_id.lower(), [])

    def get_primary_steam_id(self, package_id: str) -> Optional[str]:
        """
        获取某个 Package ID 最可能的 Steam ID。
        策略：如果有多个，这里暂时返回第一个。
        未来优化：可以根据 gameVersions 匹配当前游戏版本，返回最合适的那个。
        """
        ids = self.get_steam_ids_by_package_id(package_id)
        return ids[0] if ids else None

    # =========================================================================
    # 3. 替换逻辑 (Instead Logic)
    # =========================================================================

    def check_instead(self, mod_identifier: str, is_steam_id: bool = True, game_version: str = "1.5") -> Optional[Dict[str, Any]]:
        """
        检查某个模组是否有推荐的替换品。
        
        Args:
            mod_identifier: Steam ID 或 Package ID
            is_steam_id: 标识传入的是 ID 还是 包名
            game_version: 当前游戏版本 (用于匹配 rules 中的 oldVersions/newVersions)
        
        Returns:
            Dict: 替换规则详情, 包含 newWorkshopId, reason 等。如果没有替换则返回 None。
        """
        key = f"wid:{mod_identifier}" if is_steam_id else f"pid:{mod_identifier.lower()}"
        rules = self.instead_index.get(key, [])

        if not rules:
            return None

        # 遍历规则，寻找最匹配的一条
        for rule in rules:
            # 1. 检查版本兼容性 (如果规则里定义了 newVersions)
            new_versions = rule.get("newVersions", [])
            if new_versions and game_version not in new_versions:
                # 推荐的新模组不支持当前游戏版本，跳过推荐
                continue
            
            # 2. 返回推荐信息
            return {
                "type": "instead",
                "old_name": rule.get("oldName", "Unknown Mod"),
                "new_name": rule.get("newName"),
                "new_id": rule.get("newWorkshopId"),
                "new_package_id": rule.get("newPackageId"),
                "message": f"推荐使用 {rule.get('newName')} 替代 {rule.get('oldName')}"
            }
        
        return None

    # =========================================================================
    # 4. 协作接口: 为 mgr_mod_update.py 准备 (Collaboration)
    # =========================================================================

    def get_download_url(self, steam_id: str) -> Optional[str]:
        """获取模组的下载/详情页链接"""
        info = self.workshop_db.get(str(steam_id))
        if info:
            return info.get("url")
        # 如果数据库没记录，构建标准 Steam URL
        return f"https://steamcommunity.com/sharedfiles/filedetails/?id={steam_id}"

    def get_mod_dependencies(self, steam_id: str) -> List[Dict[str, str]]:
        """
        获取模组的依赖列表 (从社区数据库中读取，通常比本地 About.xml 更准确或即使未下载也能获取)
        
        Returns:
            [{"steam_id": "...", "name": "..."}, ...]
        """
        info = self.workshop_db.get(str(steam_id))
        if not info:
            return []
        
        # database 格式示例: "dependencies": { "2891845502": ["Alpha Genes", "url..."] }
        deps_raw = info.get("dependencies", {})
        result = []
        
        for dep_id, details in deps_raw.items():
            # details 是个 list，第一个元素通常是名字
            name = details[0] if isinstance(details, list) and len(details) > 0 else "Unknown Dependency"
            result.append({
                "steam_id": dep_id,
                "name": name
            })
        return result

    def get_latest_authors(self, package_id: str) -> str:
        """尝试获取最新的作者信息，用于填充本地缺失元数据"""
        # 优先找对应的 Steam ID
        ids = self.pkg_id_index.get(package_id.lower(), [])
        if not ids: return "Unknown"
        
        # 取第一个有作者信息的
        for sid in ids:
            info = self.workshop_db.get(sid)
            if info and "authors" in info:
                return info["authors"]
        return "Unknown"

# 全局单例
workshop_db_manager = WorkshopDBManager()