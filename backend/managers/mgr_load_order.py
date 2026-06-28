import os
import shutil
import glob
import datetime
from pathlib import Path
from typing import Any
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
from lxml import html
etree = html.etree

# 统一的排序文件格式标识，供后端解析结果和前端展示共用。
EXPORT_FORMAT_MODSCONFIG = "modsconfig"
EXPORT_FORMAT_MODLIST = "modlist"
IMPORT_FORMAT_SAVEGAME = "savegame"

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
        # self.config_dir = settings.config.game_config_path
        # self.mods_config_file = ''

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

    def _normalize_package_id(self, package_id: Any) -> str:
        # 包名统一转小写，避免不同来源文件大小写不一致导致匹配失败。
        return str(package_id or "").strip().lower()

    def _normalize_workshop_id(self, workshop_id: Any) -> str | None:
        # 0 和空值都视为“没有可用工坊ID”，前端不应把它当成可订阅项目。
        value = str(workshop_id or "").strip()
        if not value or value == "0":
            return None
        return value

    def _read_list_values(self, root, *xpaths: str) -> list[str]:
        # 多种格式节点路径不同，这里按候选 XPath 依次兼容读取。
        for xpath in xpaths:
            nodes = root.xpath(xpath)
            if not nodes:
                continue
            parent = nodes[0]
            return [str(li.text).strip() if li.text else "" for li in parent.findall("li")]
        return []

    def _read_single_text(self, root, *xpaths: str) -> str:
        # 单值节点也按候选 XPath 兼容，主要用于 ModList 的 Name。
        for xpath in xpaths:
            nodes = root.xpath(xpath)
            if not nodes:
                continue
            text = getattr(nodes[0], "text", None)
            if text:
                return str(text).strip()
        return ""

    def _build_mod_entries(self, mod_ids: list[str], mod_names: list[str] | None = None, mod_workshop_ids: list[str] | None = None):
        
        """
        构建排序文件 Mod 元数据，包括可见 Mod 数据和原始包名大小写。
        """
        # 把 modIds / modNames / workshopIds 三组平行数组整理成统一结构。
        mod_names = mod_names or []
        mod_workshop_ids = mod_workshop_ids or []
        entries = []
        for index, raw_package_id in enumerate(mod_ids):
            package_id_raw = str(raw_package_id or "").strip()
            if not package_id_raw:
                continue
            package_id = self._normalize_package_id(package_id_raw)
            name = str(mod_names[index]).strip() if index < len(mod_names) and mod_names[index] else ""
            workshop_id_raw = str(mod_workshop_ids[index]).strip() if index < len(mod_workshop_ids) and mod_workshop_ids[index] else ""
            entries.append({
                "index": index,
                "package_id": package_id,
                "package_id_raw": package_id_raw,
                "name": name,
                "workshop_id": self._normalize_workshop_id(workshop_id_raw),
                "workshop_id_raw": workshop_id_raw,
            })
        return entries

    def _enrich_mod_entries(self, entries: list[dict]):
        """
        补全排序文件 Mod 元数据，包括可见 Mod 数据和原始包名大小写。
        """
        # 读取到的文件信息可能不完整，这里负责补全名称、原始包名和工坊ID。
        if not entries: return entries
        package_ids = [entry["package_id"] for entry in entries if entry.get("package_id")]
        visible_map: dict[str, dict[str, Any]] = {}
        raw_case_map: dict[str, str] = {}
        meta_map: dict[str, dict[str, Any]] = {}
        try:
            from backend.database.dao import ModDAO
            if self.context and self.context.is_healthy:
                # 优先使用当前环境可见 Mod 数据，名称和工坊ID最贴近用户现场状态。
                for mod in ModDAO.get_profile_mods(self.context):
                    package_id = self._normalize_package_id(mod.get("package_id"))
                    if not package_id or package_id in visible_map:
                        continue
                    visible_map[package_id] = {
                        "package_id_raw": mod.get("package_id_raw") or mod.get("package_id") or package_id,
                        "name": mod.get("alias_name") or mod.get("display_name") or mod.get("name") or package_id,
                        "workshop_id": self._normalize_workshop_id(mod.get("workshop_id")),
                    }
        except Exception as e:
            logger.warning(f"补全排序文件 Mod 可见元数据失败: {e}")

        try:
            from backend.database.models import ModAsset
            # 单独回查原始包名大小写，导出时尽量保留用户更熟悉的写法。
            query = ModAsset.select(ModAsset.package_id, ModAsset.package_id_raw).where(
                ModAsset.package_id.in_(package_ids) # type: ignore
            )
            for asset in query:
                if asset.package_id and asset.package_id_raw and asset.package_id not in raw_case_map:
                    raw_case_map[asset.package_id] = asset.package_id_raw
        except Exception as e:
            logger.warning(f"补全排序文件原始包名失败: {e}")

        try:
            from backend.database.models_ext import WorkshopMeta
            # 再用离线工坊元数据兜底，给未安装项也补回名称和工坊ID。
            meta_query = (
                WorkshopMeta
                .select(WorkshopMeta.package_id, WorkshopMeta.workshop_id, WorkshopMeta.name, WorkshopMeta.title)
                .where(WorkshopMeta.package_id.in_(package_ids))
                .dicts()
            )
            for meta in meta_query:
                package_id = self._normalize_package_id(meta.get("package_id"))
                if not package_id or package_id in meta_map:
                    continue
                meta_map[package_id] = {
                    "name": meta.get("name") or meta.get("title") or package_id,
                    "workshop_id": self._normalize_workshop_id(meta.get("workshop_id")),
                }
        except Exception as e:
            logger.warning(f"补全排序文件创意工坊元数据失败: {e}")

        for entry in entries:
            # 这里采用“文件原值 > 当前环境 > 扩展库 > 兜底包名”的顺序。
            # 这样既能尊重导入文件的原始信息，又能在信息不完整时尽量补齐。
            package_id = entry.get("package_id", "")
            visible_meta = visible_map.get(package_id, {})
            workshop_meta = meta_map.get(package_id, {})

            entry["package_id_raw"] = (
                entry.get("package_id_raw")
                or raw_case_map.get(package_id)
                or visible_meta.get("package_id_raw")
                or package_id
            )
            entry["name"] = (
                entry.get("name")
                or visible_meta.get("name")
                or workshop_meta.get("name")
                or entry.get("package_id_raw")
                or package_id
            )
            entry["workshop_id"] = (
                entry.get("workshop_id")
                or visible_meta.get("workshop_id")
                or workshop_meta.get("workshop_id")
            )
            entry["workshop_id_raw"] = (
                entry.get("workshop_id_raw")
                or entry.get("workshop_id")
                or "0"
            )

        return entries

    def _parse_load_order_file(self, mods_config_file_path: str):
        """
        解析排序文件，返回 Mod ID、名称和工坊ID 列表。
        """
        # 三种格式最终都归一成同一份结构，前端不再关心原始 XML 长什么样。
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(mods_config_file_path, parser)
        root = tree.getroot()
        tag_name = str(getattr(root, "tag", "")).lower()

        format_name = EXPORT_FORMAT_MODSCONFIG
        list_name = Path(mods_config_file_path).stem
        mod_ids: list[str] = []
        mod_names: list[str] = []
        mod_workshop_ids: list[str] = []

        # 存档 .rws 的排序信息位于 savegame/meta。
        if tag_name == "savegame" or root.xpath("//meta/modIds"):
            format_name = IMPORT_FORMAT_SAVEGAME
            mod_ids = self._read_list_values(root, "./meta/modIds", "//meta/modIds")
            mod_names = self._read_list_values(root, "./meta/modNames", "//meta/modNames")
            mod_workshop_ids = self._read_list_values(root, "./meta/modSteamIds", "//meta/modSteamIds")
        # ModList.xml 会显式带出 Name、modNames 和 modSteamWorkshopIds。
        elif tag_name == "modlist" or root.xpath("//modSteamWorkshopIds") or (root.xpath("//modIds") and root.xpath("//modNames")):
            format_name = EXPORT_FORMAT_MODLIST
            list_name = self._read_single_text(root, "./Name", "//Name") or list_name
            mod_ids = self._read_list_values(root, "./modIds", "//modIds")
            mod_names = self._read_list_values(root, "./modNames", "//modNames")
            mod_workshop_ids = self._read_list_values(root, "./modSteamWorkshopIds", "//modSteamWorkshopIds")
        # ModsConfig.xml 只有 activeMods，需要后续再从数据库补名称和工坊ID。
        elif tag_name == "modsconfigdata" or root.xpath("//activeMods"):
            format_name = EXPORT_FORMAT_MODSCONFIG
            mod_ids = self._read_list_values(root, "./activeMods", "//activeMods")
        else:
            raise ValueError(f"无法识别的排序文件格式: {mods_config_file_path}")

        mods = self._enrich_mod_entries(self._build_mod_entries(mod_ids, mod_names, mod_workshop_ids))
        return {
            "format": format_name,
            "list_name": list_name,
            "mods": mods,
            "active_mods": [entry["package_id"] for entry in mods],
        }

    def _build_export_entries(self, active_ids, use_raw_ids: bool = False):
        # 导出前统一生成结构化条目，避免两个导出分支重复查库和补名。
        normalized_ids = []
        for package_id in active_ids or []:
            normalized = self._normalize_package_id(package_id)
            if normalized:
                normalized_ids.append(normalized)

        entries = self._enrich_mod_entries(self._build_mod_entries(normalized_ids))
        if not use_raw_ids:
            for entry in entries:
                entry["package_id_raw"] = entry["package_id"]
        return entries

    def _default_export_name(self, export_format: str):
        # 不同格式使用不同默认文件名前缀，方便用户区分来源。
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if export_format == EXPORT_FORMAT_MODLIST:
            return f"ModList_{timestamp}.xml"
        return f"ModsConfig_{timestamp}.xml"

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
                'mod_steam_workshop_ids': []
            }
        modify_time = int(os.path.getmtime(mods_config_file_path)*1000)
        try:
            parsed = self._parse_load_order_file(mods_config_file_path)
        except Exception as e:
            logger.error(f"读取排序文件时出错: {e}")
            # 解析失败时返回空结果而不是抛异常，
            # 由 API 层决定对前端提示“解析失败”。
            parsed = {
                "format": EXPORT_FORMAT_MODSCONFIG,
                "list_name": Path(mods_config_file_path).stem,
                "mods": [],
                "active_mods": [],
            }

        return {
            'active_mods': parsed.get('active_mods', []),
            'modify_time': modify_time,
            'format': parsed.get('format', EXPORT_FORMAT_MODSCONFIG),
            'list_name': parsed.get('list_name', Path(mods_config_file_path).stem),
            'mods': parsed.get('mods', []),
            'mod_names': [entry.get('name') or entry.get('package_id_raw') or entry.get('package_id') for entry in parsed.get('mods', [])],
            'mod_steam_workshop_ids': [entry.get('workshop_id') or '0' for entry in parsed.get('mods', [])],
        }

    def save_active_mods(self, active_ids, target_path=None, trigger_dialog=False, is_dirty=True, use_raw_ids=False, export_format: str = EXPORT_FORMAT_MODSCONFIG, list_name: str | None = None):
        """
        保存加载顺序。
        :param active_ids: Mod ID 列表
        :param target_path: 指定保存路径（绝对路径）。如果不传，默认覆盖游戏配置。
        :param trigger_dialog: 是否触发系统弹窗让用户选择保存位置。
        :param export_format: 导出格式，支持 ModsConfig.xml / ModList.xml
        :param list_name: 导出 ModList.xml 时写入的 Name
        """
        export_format = str(export_format or EXPORT_FORMAT_MODSCONFIG).strip().lower()
        if export_format not in {EXPORT_FORMAT_MODSCONFIG, EXPORT_FORMAT_MODLIST}:
            raise ValueError(f"不支持的导出格式: {export_format}")
        # 先统一整理一份可导出的结构化条目，避免不同导出分支重复查库补名。
        entries = self._build_export_entries(active_ids, use_raw_ids=use_raw_ids)
        final_raw_ids = [entry.get("package_id_raw") or entry.get("package_id") for entry in entries]
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
        elif export_format == EXPORT_FORMAT_MODLIST:
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
                for mod_id in final_raw_ids:
                    li = etree.SubElement(active_node, "li")
                    li.text = mod_id # 注意：写入时可能需要恢复原始大小写，但RimWorld通常不敏感
                # 4. 格式化写入
                tree.write(write_path, pretty_print=True, xml_declaration=True, encoding="utf-8")
                # 同步备份到 backup_root
                self._write_modlist_file(os.path.join(self.backup_root, f'Latest_ModList.xml'), entries, resolved_list_name)
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
        3. 以 ModList 格式存入备份目录。
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
            filename = f"ModList_{timestamp}.xml"
            dest_path = os.path.join(self.today_dir, filename)
            # 3. 如果已经存在同时间戳的备份，说明文件没变动，跳过
            if os.path.exists(dest_path): return
            # 4. 准备全量元数据条目 (利用 old_data 中已经补全好的 mods 列表)
            entries = old_data.get('mods', [])
            # 5. 写入 ModList 格式
            list_name = f"BeforeSave_{timestamp}"
            self._write_modlist_file(dest_path, entries, list_name)
            logger.info(f"Successfully backed up previous state to ModList format: {filename}")
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
        files = glob.glob(os.path.join(self.today_dir, "*.xml"))
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
        earlier_files = glob.glob(os.path.join(self.earlier_dir, "*.xml"))
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
        today_files = glob.glob(os.path.join(self.today_dir, "*.xml"))
        earlier_files = glob.glob(os.path.join(self.earlier_dir, "*.xml"))
        other_files = glob.glob(os.path.join(self.other_dir, "*.xml"))
        last_backup_file = Path(self.backup_root) / "Latest_ModList.xml"
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
