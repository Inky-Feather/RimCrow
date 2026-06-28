import os
import shutil
import glob
import datetime
import hashlib
from pathlib import Path
from typing import Any
from backend.database.dao import ModDAO
from backend.database.dao_ext import ExtDAO
from backend.load_order import (
    FORMAT_MODLIST,
    FORMAT_MODSCONFIG,
    FORMAT_RML,
    FORMAT_SAVEGAME,
    FORMAT_SHARE_CODE,
    ParsedLoadOrderData,
    build_import_check_report,
    build_share_code,
    describe_share_code,
    parse_load_order_file,
    parse_share_code,
)
from backend.database.models_ext import ModReplacement
from backend.managers.mgr_profile import ProfileContext
from backend.utils.logger import logger

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径正确
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.managers.mgr_files import FileManager
from backend.settings import settings
from backend.utils.tools import normalize_package_id, normalize_workshop_id
from lxml import html
etree = html.etree

EXPORT_FORMAT_MODSCONFIG = FORMAT_MODSCONFIG
EXPORT_FORMAT_MODLIST = FORMAT_MODLIST
EXPORT_FORMAT_RML = FORMAT_RML
IMPORT_FORMAT_SAVEGAME = FORMAT_SAVEGAME
IMPORT_FORMAT_SHARE_CODE = FORMAT_SHARE_CODE

# load order 导入支持的文件类型，供 API 层弹原生文件选择框时复用。
LOAD_ORDER_OPEN_FILE_TYPES = (
    'Load Order Files (*.xml;*.rws;*.rml;*.json;*.txt;*.list)',
    'XML Files (*.xml;*.rws;*.rml)',
    'JSON Files (*.json)',
    'Text Files (*.txt;*.list)',
    'All Files (*.*)',
)

class LoadOrderManager:
    """
    负责管理 ModsConfig.xml (加载顺序)
    功能：读取当前激活列表、保存列表、自动备份
    1. 当天：保留所有操作备份。
    2. 过去：只保留当天的最后一份。
    3. 过期：删除超过 30 天的备份（除了最后一份）。
    4. 兜底：永远保留最新的一份备份。
    """
    
    def __init__(self, context: ProfileContext):
        # 从全局配置获取路径
        self.context = context
        self._ensure_dirs()

    def _ensure_dirs(self):
        # 当前环境健康时才触碰游戏配置目录；只读查看其它环境备份时不应顺手重建失效路径。
        if self.context.is_healthy:
            os.makedirs(self.context.game_config_path, exist_ok=True)
        os.makedirs(self.context.backup_dir, exist_ok=True)
        self._init_backup_dirs()

    def _init_backup_dirs(self):
        """初始化备份目录结构"""
        # 在软件目录下用 backups 文件夹存储备份
        self.backup_root = str(Path(self.context.backup_dir))
        self.today_dir = str(Path(self.context.backup_dir) / "today")
        self.earlier_dir = str(Path(self.context.backup_dir) / "earlier")
        self.other_dir = str(Path(self.context.backup_dir) / "other")
        
        # 创建目录
        os.makedirs(self.today_dir, exist_ok=True)
        os.makedirs(self.earlier_dir, exist_ok=True)
        os.makedirs(self.other_dir, exist_ok=True)
        
        # 每次初始化（应用启动）时执行一次轮换检查
        self._rotate_backups()

    def _normalize_workshop_id(self, workshop_id: Any) -> str | None:
        # 0 和空值都视为“没有可用工坊ID”，前端不应把它当成可订阅项目。
        value = normalize_workshop_id(workshop_id)
        return value or None

    def _normalize_source_url(self, source_url: Any) -> str | None:
        value = str(source_url or "").strip()
        return value or None

    def _build_mod_entries(
        self,
        mod_ids: list[str],
        mod_names: list[str] | None = None,
        mod_workshop_ids: list[str] | None = None,
        mod_source_urls: list[str] | None = None,
    ):
        
        """
        构建排序文件 Mod 元数据，包括可见 Mod 数据和原始包名大小写。
        """
        # 把 modIds / modNames / workshopIds 三组平行数组整理成统一结构。
        mod_names = mod_names or []
        mod_workshop_ids = mod_workshop_ids or []
        mod_source_urls = mod_source_urls or []
        entries = []
        for index, raw_package_id in enumerate(mod_ids):
            package_id_raw = str(raw_package_id or "").strip()
            if not package_id_raw:
                continue
            package_id = normalize_package_id(package_id_raw)
            name = str(mod_names[index]).strip() if index < len(mod_names) and mod_names[index] else ""
            workshop_id_raw = str(mod_workshop_ids[index]).strip() if index < len(mod_workshop_ids) and mod_workshop_ids[index] else ""
            source_url_raw = str(mod_source_urls[index]).strip() if index < len(mod_source_urls) and mod_source_urls[index] else ""
            entries.append({
                "index": index,
                "package_id": package_id,
                "package_id_raw": package_id_raw,
                "name": name,
                "workshop_id": self._normalize_workshop_id(workshop_id_raw),
                "workshop_id_raw": workshop_id_raw,
                "source_url": self._normalize_source_url(source_url_raw),
                "source_url_raw": source_url_raw,
            })
        return entries

    def _load_replacements_by_workshop_id(self, workshop_ids: list[str]):
        """
        批量读取“旧 workshop id -> 替代规则”的映射。

        这一步只做数据准备，不在这里判断状态；状态判断交给纯逻辑模块，
        这样后续更容易补测试。
        """
        valid_ids = [wid for wid in (self._normalize_workshop_id(wid) for wid in workshop_ids) if wid]
        if not valid_ids:
            return {}
        try:
            query = (
                ModReplacement
                .select(
                    ModReplacement.old_workshop_id,
                    ModReplacement.old_package_id,
                    ModReplacement.new_workshop_id,
                    ModReplacement.new_package_id,
                    ModReplacement.new_name,
                    ModReplacement.new_versions,
                )
                .where(ModReplacement.old_workshop_id.in_(valid_ids))
                .dicts()
            )
            return {
                str(row["old_workshop_id"]): row
                for row in query
                if row.get("old_workshop_id")
            }
        except Exception as e:
            logger.warning(f"读取替代规则失败: {e}")
            return {}

    def _get_visible_installed_mods(self) -> list[dict[str, Any]]:
        """
        返回当前环境中“实际生效”的已安装模组。

        这里必须使用 `ModDAO.get_profile_mods()`，而不是全库资产：
        - 只统计当前 Profile 路径范围内的模组
        - 只统计当前 Profile 启用域内可见的模组
        - 自动排除被同包名高优先级路径遮蔽的副本
        - 自动排除物理禁用/失效条目

        导入检查、缺失安装判断都必须以这个集合为准，否则会把“数据库里存在但当前环境无效”的条目误判成已安装。
        """
        if not self.context:
            return []
        return ModDAO.get_profile_mods(self.context)

    def _build_import_check(self, parsed: ParsedLoadOrderData):
        """
        构建导入检查报告。

        注意这里依赖当前环境上下文，因为“缺失 / 替代 / 其它版本”都必须以
        “当前环境实际可见的安装项”为参考。
        """
        if not self.context:
            return {"summary": {}, "items": []}

        try:
            installed_mods = self._get_visible_installed_mods()
        except Exception as e:
            logger.warning(f"读取当前环境模组失败，无法构建导入检查报告: {e}")
            return {"summary": {}, "items": []}

        details_by_package_id = {}
        try:
            details_by_package_id = ExtDAO.get_workshop_details_by_package_ids(
                parsed.package_ids,
                current_game_version=self.context.game_version if self.context else "",
            )
        except Exception as e:
            logger.warning(f"读取包名补全详情失败: {e}")

        details_by_workshop_id = {}
        try:
            details_by_workshop_id = ExtDAO.get_workshop_details_by_workshop_ids(parsed.workshop_ids)
        except Exception as e:
            logger.warning(f"读取工坊详情失败: {e}")

        replacements_by_workshop_id = self._load_replacements_by_workshop_id(parsed.workshop_ids)
        return build_import_check_report(
            parsed,
            installed_mods=installed_mods,
            details_by_package_id=details_by_package_id,
            details_by_workshop_id=details_by_workshop_id,
            replacements_by_old_workshop_id=replacements_by_workshop_id,
            game_version=self.context.game_version,
        )

    def _enrich_mod_entries(self, entries: list[dict]):
        """
        补全排序文件 Mod 元数据，包括可见 Mod 数据和原始包名大小写。
        """
        # 读取到的文件信息可能不完整，这里负责补全名称、原始包名和工坊ID。
        if not entries: return entries
        package_ids = [entry["package_id"] for entry in entries if entry.get("package_id")]
        visible_map: dict[str, dict[str, Any]] = {}
        asset_map: dict[str, dict[str, Any]] = {}
        meta_map: dict[str, dict[str, Any]] = {}
        try:
            from backend.database.dao import ModDAO
            if self.context and self.context.is_healthy:
                # 优先使用当前环境可见 Mod 数据，名称和工坊ID最贴近用户现场状态。
                for mod in self._get_visible_installed_mods():
                    package_id = normalize_package_id(mod.get("package_id"))
                    if not package_id or package_id in visible_map:
                        continue
                    visible_map[package_id] = {
                        "package_id_raw": mod.get("package_id_raw") or mod.get("package_id") or package_id,
                        "name": mod.get("name") or package_id,
                        "alias_name": mod.get("alias_name") or mod.get("display_name") or mod.get("name") or package_id,
                        "workshop_id": self._normalize_workshop_id(mod.get("workshop_id")),
                        "source_url": self._normalize_source_url(mod.get("url")),
                    }
        except Exception as e:
            logger.warning(f"补全排序文件 Mod 可见元数据失败: {e}")

        try:
            from backend.database.models import ModAsset
            # 再单独回查资产缓存，给缺失项补原始包名、来源 URL 等元数据。
            query = ModAsset.select(
                ModAsset.package_id,
                ModAsset.package_id_raw,
                ModAsset.name,
                ModAsset.workshop_id,
                ModAsset.url,
            ).where(
                ModAsset.package_id.in_(package_ids) # type: ignore
            )
            for asset in query.dicts():
                package_id = normalize_package_id(asset.get("package_id"))
                if not package_id or package_id in asset_map:
                    continue
                asset_map[package_id] = {
                    "package_id_raw": asset.get("package_id_raw") or package_id,
                    "name": asset.get("name") or package_id,
                    "workshop_id": self._normalize_workshop_id(asset.get("workshop_id")),
                    "source_url": self._normalize_source_url(asset.get("url")),
                }
        except Exception as e:
            logger.warning(f"补全排序文件原始包名失败: {e}")

        try:
            # 这里不能再直接按 package_id 读取 WorkshopMeta，
            # 否则会把 replacement 共用包名的 workshop_id 混进“原版补全”。
            detail_map = ExtDAO.get_workshop_details_by_package_ids(
                package_ids,
                current_game_version=self.context.game_version if self.context else "",
            )
            for package_id, lookup in detail_map.items():
                direct_detail = ((lookup or {}).get("direct") or {}).get("selected") or {}
                direct_workshop_id = self._normalize_workshop_id(direct_detail.get("workshop_id"))
                direct_name = str(direct_detail.get("name") or "").strip()
                if not package_id or (not direct_name and not direct_workshop_id):
                    continue
                meta_map[package_id] = {
                    "name": direct_name or package_id,
                    "workshop_id": direct_workshop_id,
                }
        except Exception as e:
            logger.warning(f"补全排序文件创意工坊元数据失败: {e}")

        for entry in entries:
            # 这里采用“文件原值 > 当前环境 > 扩展库 > 兜底包名”的顺序。
            # 这样既能尊重导入文件的原始信息，又能在信息不完整时尽量补齐。
            package_id = entry.get("package_id", "")
            visible_meta = visible_map.get(package_id, {})
            asset_meta = asset_map.get(package_id, {})
            workshop_meta = meta_map.get(package_id, {})

            entry["package_id_raw"] = (
                entry.get("package_id_raw")
                or visible_meta.get("package_id_raw")
                or asset_meta.get("package_id_raw")
                or package_id
            )
            entry["name"] = (
                entry.get("name")
                or visible_meta.get("name")
                or asset_meta.get("name")
                or workshop_meta.get("name")
                or entry.get("package_id_raw")
                or package_id
            )
            entry["workshop_id"] = (
                entry.get("workshop_id")
                or visible_meta.get("workshop_id")
                or asset_meta.get("workshop_id")
                or workshop_meta.get("workshop_id")
            )
            # raw 字段只代表文件原始记录，不能被后续库补全覆盖。
            entry["workshop_id_raw"] = entry.get("workshop_id_raw") or "0"
            entry["source_url"] = (
                entry.get("source_url")
                or visible_meta.get("source_url")
                or asset_meta.get("source_url")
            )
            entry["source_url_raw"] = entry.get("source_url_raw") or ""

        return entries

    def _build_entries_from_parsed(self, parsed: ParsedLoadOrderData):
        """
        把纯解析结果转成当前项目内部使用的结构化 mod 条目。

        `backend.load_order` 不依赖数据库，也不关心当前 profile；
        这里才是“结合本项目上下文补全信息”的地方。
        """
        mods = self._enrich_mod_entries(
            self._build_mod_entries(parsed.package_ids, parsed.mod_names, parsed.workshop_ids, parsed.source_urls)
        )
        return {
            "format": parsed.format,
            "list_name": parsed.list_name,
            "mods": mods,
            "active_mods": [entry["package_id"] for entry in mods],
            "mod_names": [entry.get("name") or entry.get("package_id_raw") or entry.get("package_id") for entry in mods],
            "mod_steam_workshop_ids": [entry.get("workshop_id") or "0" for entry in mods],
            "source_urls": [entry.get("source_url") or "" for entry in mods],
            "warnings": list(parsed.warnings),
            "errors": list(parsed.errors),
        }

    def _build_read_result_from_parsed(self, parsed: ParsedLoadOrderData, modify_time: int = 0, source_path: str = ""):
        """
        把“文件解析结果 / 分享码解析结果”统一整理成 API 可直接返回的结构。

        这样文件导入和分享码导入就不会各自维护一套字段拼装逻辑。
        """
        parsed_result = self._build_entries_from_parsed(parsed)
        import_check = self._build_import_check(parsed)
        return {
            'active_mods': parsed_result.get('active_mods', []),
            'modify_time': modify_time,
            'format': parsed_result.get('format', EXPORT_FORMAT_MODSCONFIG),
            'list_name': parsed_result.get('list_name', Path(source_path).stem if source_path else ''),
            'mods': parsed_result.get('mods', []),
            'mod_names': parsed_result.get('mod_names', []),
            'mod_steam_workshop_ids': parsed_result.get('mod_steam_workshop_ids', []),
            'source_urls': parsed_result.get('source_urls', []),
            'workshop_ids': list(parsed.workshop_ids),
            'warnings': parsed_result.get('warnings', []),
            'errors': parsed_result.get('errors', []),
            'import_check': import_check,
            'source_path': source_path,
            'version_token': self._build_version_token(source_path, parsed_result.get('active_mods', []), modify_time=modify_time),
        }

    def _build_export_entries(self, active_ids):
        # 导出前统一生成结构化条目，避免两个导出分支重复查库和补名。
        normalized_ids = []
        for package_id in active_ids or []:
            normalized = normalize_package_id(package_id)
            if normalized:
                normalized_ids.append(normalized)

        entries = self._enrich_mod_entries(self._build_mod_entries(normalized_ids))
        for entry in entries:
            # 游戏原生读写与本工具内部持久化一律使用规范化小写包名。
            entry["package_id_raw"] = entry["package_id"]
        return entries

    def _build_active_ids_hash(self, active_ids: list[str] | None = None) -> str:
        normalized_ids = [normalize_package_id(package_id) for package_id in (active_ids or [])]
        normalized_ids = [package_id for package_id in normalized_ids if package_id]
        joined = "\n".join(normalized_ids)
        return hashlib.sha1(joined.encode("utf-8")).hexdigest()

    def _build_version_token(self, file_path: str | None, active_ids: list[str] | None = None, modify_time: int | None = None):
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return {
                "path": "",
                "mtime_ms": int(modify_time or 0),
                "size": 0,
                "active_hash": self._build_active_ids_hash(active_ids),
            }
        file_size = 0
        file_mtime = int(modify_time or 0)
        if os.path.exists(normalized_path):
            try:
                stat = os.stat(normalized_path)
                file_size = int(stat.st_size)
                if not file_mtime:
                    file_mtime = int(stat.st_mtime * 1000)
            except OSError:
                file_size = 0
        return {
            "path": normalized_path,
            "mtime_ms": file_mtime,
            "size": file_size,
            "active_hash": self._build_active_ids_hash(active_ids),
        }

    def get_current_version_token(self, mods_config_file_path: str | None = None):
        read_result = self.read_active_mods(mods_config_file_path)
        return read_result.get("version_token", {})

    def is_version_token_stale(self, base_version_token: dict | None = None, mods_config_file_path: str | None = None):
        expected = dict(base_version_token or {})
        current = self.get_current_version_token(mods_config_file_path)
        if not expected:
            return False, current
        return current != expected, current

    def export_share_code(self, active_ids, list_name: str | None = None) -> str:
        """
        导出分享码。

        这里仍复用 manager 的元数据补全过程，让分享码尽量携带名称和工坊 ID，
        但真正的编码规则交给 `backend.load_order.share_code`。
        """
        entries = self._build_export_entries(active_ids)
        if not entries:
            raise ValueError("当前没有可生成分享码的模组")

        resolved_list_name = str(list_name or "").strip() or "Shared Load Order"
        return build_share_code(
            package_ids=[entry.get("package_id") or "" for entry in entries],
            mod_names=[entry.get("name") or "" for entry in entries],
            workshop_ids=[entry.get("workshop_id") or "" for entry in entries],
            list_name=resolved_list_name,
            game_version=self.context.game_version or "",
        )

    def read_share_code(self, share_code: str):
        """
        读取分享码并返回与 `read_active_mods` 对齐的结果结构。
        """
        parsed = parse_share_code(share_code)
        result = self._build_read_result_from_parsed(parsed, modify_time=0, source_path=describe_share_code(share_code))
        result["share_code"] = str(share_code or "").strip()
        result["share_code_ref"] = describe_share_code(share_code)
        return result

    def _default_export_name(self, export_format: str):
        # 不同格式使用不同默认文件名前缀，方便用户区分来源。
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if export_format == EXPORT_FORMAT_RML:
            return f"ModList_{timestamp}.rml"
        if export_format == EXPORT_FORMAT_MODLIST:
            return f"ModList_{timestamp}.xml"
        return f"ModsConfig_{timestamp}.xml"

    def _get_save_file_types(self, export_format: str):
        # 保存对话框根据目标格式切换默认过滤器，避免用户手动改后缀。
        if export_format == EXPORT_FORMAT_RML:
            return ('RML Files (*.rml)', 'All Files (*.*)')
        return ('XML Files (*.xml)', 'All Files (*.*)')

    def _write_modlist_file(self, write_path: str, entries: list[dict], list_name: str):
        # ModList.xml 需要显式写出名称和工坊ID，后续导入时才能直接一键订阅。
        root = etree.Element("ModList")
        name_node = etree.SubElement(root, "Name")
        name_node.text = list_name or Path(write_path).stem or "ModList"

        mod_ids_node = etree.SubElement(root, "modIds")
        mod_names_node = etree.SubElement(root, "modNames")
        workshop_ids_node = etree.SubElement(root, "modSteamWorkshopIds")

        for entry in entries:
            etree.SubElement(mod_ids_node, "li").text = entry.get("package_id_raw") or entry.get("package_id")
            etree.SubElement(mod_names_node, "li").text = entry.get("name") or entry.get("package_id_raw") or entry.get("package_id")
            etree.SubElement(workshop_ids_node, "li").text = entry.get("workshop_id") or "0"

        tree = etree.ElementTree(root)
        tree.write(write_path, pretty_print=True, xml_declaration=True, encoding="utf-8")

    def _write_rml_file(self, write_path: str, entries: list[dict]):
        """
        写出 RimWorld 原生 `.rml` 列表。

        之所以把自动备份切到 RML，是因为它保留了：
        - package_id
        - workshop_id
        - 模组名称
        - gameVersion
        并且更贴近游戏自己的列表格式。
        """

        root = etree.Element("savedModList")
        meta_node = etree.SubElement(root, "meta")
        game_version_node = etree.SubElement(meta_node, "gameVersion")
        game_version_node.text = self.context.game_version or ""

        mod_ids_node = etree.SubElement(meta_node, "modIds")
        mod_steam_ids_node = etree.SubElement(meta_node, "modSteamIds")
        mod_names_node = etree.SubElement(meta_node, "modNames")

        mod_list_node = etree.SubElement(root, "modList")
        ids_node = etree.SubElement(mod_list_node, "ids")
        names_node = etree.SubElement(mod_list_node, "names")

        for entry in entries:
            package_id = entry.get("package_id_raw") or entry.get("package_id") or ""
            display_name = entry.get("name") or package_id
            workshop_id = entry.get("workshop_id") or "0"

            etree.SubElement(mod_ids_node, "li").text = package_id
            etree.SubElement(mod_steam_ids_node, "li").text = workshop_id
            etree.SubElement(mod_names_node, "li").text = display_name
            etree.SubElement(ids_node, "li").text = package_id
            etree.SubElement(names_node, "li").text = display_name

        tree = etree.ElementTree(root)
        tree.write(write_path, pretty_print=True, xml_declaration=True, encoding="utf-8")

    def read_active_mods(self, mods_config_file_path=None):
        """
        读取排序文件并返回统一结构。
        返回值不仅包含 active_mods，还会包含：
        - format：文件格式标识
        - list_name：列表名称/文件标题
        - mods：结构化模组条目，供前端显示名称和一键订阅
        """
        if not mods_config_file_path:
            mods_config_file_path = self.context.mods_config_file
        if not mods_config_file_path or not os.path.exists(mods_config_file_path):
            logger.warning(f"ModsConfig.xml not found: {mods_config_file_path}")
            return {
                'active_mods': [],
                'modify_time': 0,
                'format': EXPORT_FORMAT_MODSCONFIG,
                'list_name': Path(mods_config_file_path).stem if mods_config_file_path else '',
                'mods': [],
                'mod_names': [],
                'mod_steam_workshop_ids': [],
                'source_urls': [],
                'workshop_ids': [],
                'warnings': [],
                'errors': [],
                'version_token': self._build_version_token(mods_config_file_path, []),
            }
        modify_time = int(os.path.getmtime(mods_config_file_path)*1000)
        try:
            parsed = parse_load_order_file(mods_config_file_path)
            return self._build_read_result_from_parsed(
                parsed,
                modify_time=modify_time,
                source_path=mods_config_file_path,
            )
        except Exception as e:
            logger.error(f"读取排序文件时出错: {e}")
            # 解析失败时返回空结果而不是抛异常，由 API 层决定对前端提示“解析失败”。
            return {
                'active_mods': [],
                'modify_time': modify_time,
                "format": EXPORT_FORMAT_MODSCONFIG,
                "list_name": Path(mods_config_file_path).stem if mods_config_file_path else "",
                "mods": [],
                "mod_names": [],
                "mod_steam_workshop_ids": [],
                "source_urls": [],
                "workshop_ids": [],
                "warnings": [],
                "errors": [str(e)],
                'import_check': {"summary": {}, "items": []},
                'version_token': self._build_version_token(mods_config_file_path, [], modify_time=modify_time),
            }

    def save_active_mods(self, active_ids, target_path=None, trigger_dialog=False, is_dirty=True, export_format: str = EXPORT_FORMAT_MODSCONFIG, list_name: str | None = None):
        """
        保存加载顺序。
        :param active_ids: Mod ID 列表
        :param target_path: 指定保存路径（绝对路径）。如果不传，默认覆盖游戏配置。
        :param trigger_dialog: 是否触发系统弹窗让用户选择保存位置。
        :param export_format: 导出格式，支持 ModsConfig.xml / ModList.xml / RML
        :param list_name: 导出 ModList.xml 时写入的 Name
        """
        export_format = str(export_format or EXPORT_FORMAT_MODSCONFIG).strip().lower()
        if export_format not in {EXPORT_FORMAT_MODSCONFIG, EXPORT_FORMAT_MODLIST, EXPORT_FORMAT_RML}:
            raise ValueError(f"不支持的导出格式: {export_format}")
        # 先统一整理一份可导出的结构化条目，避免不同导出分支重复查库补名。
        entries = self._build_export_entries(active_ids)
        final_ids = [entry.get("package_id") or "" for entry in entries]
        default_name = self._default_export_name(export_format)
        # 1. 确定最终写入路径
        write_path = self.context.mods_config_file if export_format == EXPORT_FORMAT_MODSCONFIG else ''
        if trigger_dialog:
            # 弹出对话框选择路径
            # 默认文件名带上时间戳或有意义的名字
            parent_dir = os.path.dirname(str(target_path)) if target_path else self.other_dir
            selected = FileManager.save_file_dialog(
                initial_dir=parent_dir or self.other_dir,
                default_filename=default_name,
                file_types=self._get_save_file_types(export_format),
            )
            logger.info(f"用户选择保存路径: {selected}")
            if not selected: return 
            write_path = selected
        elif target_path:
            # 指定了路径（用于恢复备份等内部逻辑）
            # 确保父目录存在
            parent_dir = os.path.dirname(target_path)
            if not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir)
                except OSError:
                    logger.error(f"无法创建目录: {parent_dir}")
                    raise Exception(f"无法创建目录: {parent_dir}")
            write_path = target_path
        elif export_format in {EXPORT_FORMAT_MODLIST, EXPORT_FORMAT_RML}:
            write_path = os.path.join(self.other_dir, default_name)
        if not write_path: raise Exception("未指定有效保存路径")
        resolved_list_name = (list_name or Path(write_path).stem or default_name).strip()
        # 2. 只有在覆盖默认配置时并且 is_dirty 为 True 时，才需要自动备份旧文件
        # 如果是另存为，没必要备份目标文件（通常目标文件不存在）
        if export_format == EXPORT_FORMAT_MODSCONFIG and write_path == self.context.mods_config_file and is_dirty:
            self._create_backup()
        # 3. 准备 XML 结构 (逻辑保持不变)
        current_version = self.context.game_version
        try:
            if export_format == EXPORT_FORMAT_MODLIST:
                # ModList.xml 是完全新建的导出文件，不需要继承现有 ModsConfig.xml 结构。
                self._write_modlist_file(write_path, entries, resolved_list_name)
                logger.info(f"成功导出 {len(entries)} 个模组到 ModList.xml: {write_path}")
            elif export_format == EXPORT_FORMAT_RML:
                # RML 更接近 RimWorld 自己的列表格式，也适合作为长期可读的备份格式。
                self._write_rml_file(write_path, entries)
                logger.info(f"成功导出 {len(entries)} 个模组到 RML: {write_path}")
            else:
                # 尝试保留原有的 knownExpansions 等信息
                parser = etree.XMLParser(remove_blank_text=True)
                if os.path.exists(self.context.mods_config_file):
                    tree = etree.parse(self.context.mods_config_file, parser)
                    root = tree.getroot()
                else:
                    # 如果文件不存在，创建基本骨架
                    root = etree.Element("ModsConfigData")
                    # 尝试从 settings 获取版本，或者默认 Unknow
                    ver = etree.SubElement(root, "version")
                    ver.text = current_version # 这是一个兜底，理想情况应该读 Version.txt
                    etree.SubElement(root, "activeMods")
                    etree.SubElement(root, "knownExpansions")
                    tree = etree.ElementTree(root)
                # 更新 activeMods 节点，没有则创建
                active_node = root.find("activeMods")
                if active_node is None:
                    active_node = etree.SubElement(root, "activeMods")
                # 清空旧列表
                active_node.clear()
                # ModsConfig.xml 仍保持游戏原生结构，只更新 activeMods 节点。
                for mod_id in final_ids:
                    li = etree.SubElement(active_node, "li")
                    li.text = mod_id
                # 4. 格式化写入
                tree.write(write_path, pretty_print=True, xml_declaration=True, encoding="utf-8")
                # 同步一份最近备份，改用 RML 格式，方便后续完整恢复和识别。
                self._write_rml_file(os.path.join(self.backup_root, "Latest_ModList.rml"), entries)
                logger.info(f"成功保存 {len(active_ids)} 个模组到: {write_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存排序文件时出错：{e}")
            raise Exception(f"保存排序文件时出错：{e}")

    def _create_backup(self):
        """
        [核心重构] 备份当前磁盘上的旧状态：
        1. 读取磁盘上现有的 ModsConfig.xml。
        2. 解析并利用数据库补全元数据（Name, WorkshopID）。
        3. 以 RML 格式存入备份目录。
        """
        # 只有当旧文件存在时才有备份价值
        old_file_path = self.context.mods_config_file
        if not old_file_path or not os.path.exists(old_file_path): return
        try:
            # 1. 读取并解析当前磁盘上的旧文件
            # 利用现有的 read_active_mods 逻辑，它已经包含了从 DB 补全信息的能力
            old_data = self.read_active_mods(old_file_path)
            old_active_ids = old_data.get('active_mods', [])
            if not old_active_ids: return
            # 2. 生成备份文件名（使用旧文件的最后修改时间，这样备份更精准）
            mtime = os.path.getmtime(old_file_path)
            dt = datetime.datetime.fromtimestamp(mtime)
            timestamp = dt.strftime("%Y%m%d_%H%M%S")
            filename = f"ModList_{timestamp}.rml"
            dest_path = os.path.join(self.today_dir, filename)
            # 3. 如果已经存在同时间戳的备份，说明文件没变动，跳过
            if os.path.exists(dest_path): return
            # 4. 准备全量元数据条目 (利用 old_data 中已经补全好的 mods 列表)
            entries = old_data.get('mods', [])
            # 5. 写入 RML 格式
            self._write_rml_file(dest_path, entries)
            logger.info(f"Successfully backed up previous state to RML format: {filename}")
        except Exception as e:
            logger.error(f"Failed to create pre-save backup: {e}")

    def _rotate_backups(self):
        """
        备份轮换策略：
        - today 文件夹只保留"今天"的文件，过期的移入 earlier。
        - earlier 文件夹里，每一天只保留最后一份备份。
        - 清理超过 retention_days 的备份。
        """
        today_str = datetime.date.today().strftime("%Y%m%d")
        # 1. 移动过期的 today -> earlier
        files = glob.glob(os.path.join(self.today_dir, "*.xml")) + glob.glob(os.path.join(self.today_dir, "*.rml"))
        # 按日期分组文件的辅助字典 { "20231101": ["path1", "path2"] }
        files_by_date = {}
        for f in files:
            basename = os.path.basename(f)
            # 解析文件名中的日期 ModsConfig_YYYYMMDD_HHMMSS.xml
            try:
                # 提取 YYYYMMDD (索引 11到19)
                parts = basename.split('_')
                if len(parts) >= 2:
                    date_part = parts[1] # YYYYMMDD
                    if date_part != today_str: # 只处理旧文件
                        if date_part not in files_by_date:
                            files_by_date[date_part] = []
                        files_by_date[date_part].append(f)
            except: continue
        # 处理非今天的旧文件
        for date_str, file_list in files_by_date.items():
            # 按文件名排序（包含时间，所以最后面的就是最晚的）
            file_list.sort()
            # 保留最后一个，移入 earlier
            last_file = file_list[-1]
            try:
                shutil.move(last_file, os.path.join(self.earlier_dir, os.path.basename(last_file)))
            except: pass
            # 删除其余
            for f in file_list[:-1]:
                try: os.remove(f)
                except: pass
        # 2. 清理 earlier 中超过保留天数的文件
        # 假设保留天数在 settings 中
        retention_days = settings.config.backup_retention_days
        earlier_files = glob.glob(os.path.join(self.earlier_dir, "*.xml")) + glob.glob(os.path.join(self.earlier_dir, "*.rml"))
        cutoff_date = datetime.date.today() - datetime.timedelta(days=retention_days)
        cutoff_str = cutoff_date.strftime("%Y%m%d")
        for f in earlier_files:
            basename = os.path.basename(f)
            try:
                parts = basename.split('_')
                if len(parts) >= 2:
                    date_part = parts[1]
                    if date_part < cutoff_str:
                        os.remove(f) # 过期删除
            except: pass

    def get_all_backups(self):
        """获取所有备份文件路径"""
        today_files = glob.glob(os.path.join(self.today_dir, "*.xml")) + glob.glob(os.path.join(self.today_dir, "*.rml"))
        earlier_files = glob.glob(os.path.join(self.earlier_dir, "*.xml")) + glob.glob(os.path.join(self.earlier_dir, "*.rml"))
        other_files = glob.glob(os.path.join(self.other_dir, "*.xml")) + glob.glob(os.path.join(self.other_dir, "*.rml"))
        last_backup_file = Path(self.backup_root) / "Latest_ModList.rml"
        if not last_backup_file.is_file():
            last_backup_file = ''
        
        def build_items(files):
            return [{
                'path': f,
                'modify_time': int(os.path.getmtime(f)*1000),
                'source_profile_id': self.context.profile_id,
            } for f in files]
        result = {
            "today": build_items(today_files),
            "earlier": build_items(earlier_files),
            "other": build_items(other_files),
            "last_backup": build_items([str(last_backup_file)]) if last_backup_file else []
        }
        return result



if __name__ == "__main__":
    # mgr = LoadOrderManager()
    # a = mgr.read_active_mods(r"C:\Users\Administrator\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Saves\林亚.rws")
    # print(a)
    
    pass
