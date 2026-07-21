import os
import shutil
import datetime
import hashlib
import threading
import tempfile
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
from backend.load_order.package_tokens import parse_package_token
from backend.database.models_ext import ModReplacement
from backend.managers.mgr_profile import ProfileContext
from backend.i18n.messages import tr
from backend.utils.logger import logger

_BACKUP_LOCK = threading.RLock()
_BACKUP_PROTECTION_HOURS = 6
_BACKUP_FILE_SUFFIXES = {".xml", ".rml"}

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
from backend.utils.tools import CURRENT_COMPANION_PACKAGE_ID, normalize_companion_package_id, normalize_package_id, normalize_workshop_id
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
    
    def __init__(self, context: ProfileContext, rotate_backups: bool = False):
        # 从全局配置获取路径
        self.context = context
        # 备份是保存排序时的附带保护；失败要反馈给 API，但不能伪装成主文件保存失败。
        self.last_backup_error = ""
        self._ensure_dirs(rotate_backups=rotate_backups)

    def _ensure_dirs(self, *, rotate_backups: bool = False):
        # 当前环境健康时才触碰游戏配置目录；只读查看其它环境备份时不应顺手重建失效路径。
        if self.context.is_healthy:
            os.makedirs(self.context.game_config_path, exist_ok=True)
        os.makedirs(self.context.backup_dir, exist_ok=True)
        self._init_backup_dirs(rotate_backups=rotate_backups)

    def _init_backup_dirs(self, *, rotate_backups: bool = False):
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
        
        # 备份流转只属于备份目录维护；单纯读取列表和保存排序都不顺手改备份目录。
        if rotate_backups:
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
        package_tokens: list[str] | None = None,
        mod_names: list[str] | None = None,
        mod_workshop_ids: list[str] | None = None,
        mod_source_urls: list[str] | None = None,
    ):
        
        """
        构建排序文件 Mod 元数据，包括可见 Mod 数据和原始包名大小写。
        """
        # 把 modIds / modNames / workshopIds 三组平行数组整理成统一结构。
        package_tokens = package_tokens or []
        mod_names = mod_names or []
        mod_workshop_ids = mod_workshop_ids or []
        mod_source_urls = mod_source_urls or []
        entries = []
        seen_package_ids = set()
        for index, raw_package_id in enumerate(mod_ids):
            package_token_raw = str(
                package_tokens[index]
                if index < len(package_tokens) and package_tokens[index]
                else raw_package_id
            ).strip()
            token_info = parse_package_token(package_token_raw or raw_package_id)
            package_id_raw = str(raw_package_id or "").strip()
            package_id = normalize_companion_package_id(token_info.canonical_package_id or package_id_raw)
            if not package_id or package_id in seen_package_ids:
                continue
            seen_package_ids.add(package_id)
            name = str(mod_names[index]).strip() if index < len(mod_names) and mod_names[index] else ""
            workshop_id_raw = str(mod_workshop_ids[index]).strip() if index < len(mod_workshop_ids) and mod_workshop_ids[index] else ""
            source_url_raw = str(mod_source_urls[index]).strip() if index < len(mod_source_urls) and mod_source_urls[index] else ""
            entries.append({
                "index": index,
                "package_id": package_id,
                "package_id_raw": package_id_raw,
                # `_local` 只做兼容读取，不继续向前端和保存流程传播。
                "package_token": (
                    token_info.normalized_token
                    if token_info.source_preference == "steam" and package_id != CURRENT_COMPANION_PACKAGE_ID
                    else package_id
                ),
                "package_token_raw": package_token_raw or package_id_raw or package_id,
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
        if not valid_ids: return {}
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
        if not self.context: return []
        return ModDAO.get_profile_mods(self.context)

    def _build_import_check(self, parsed: ParsedLoadOrderData):
        """
        构建导入检查报告。

        注意这里依赖当前环境上下文，因为“缺失 / 替代 / 其它版本”都必须以
        “当前环境实际可见的安装项”为参考。
        """
        if not self.context: return {"summary": {}, "items": []}

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

        install_sources_by_package_id = {}
        try:
            install_sources_by_package_id = ExtDAO.get_install_sources_by_package_ids(
                parsed.package_ids,
                current_game_version=self.context.game_version if self.context else "",
            )
        except Exception as e:
            logger.warning(f"读取包名安装来源失败: {e}")

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
            install_sources_by_package_id=install_sources_by_package_id,
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
                    workshop_variant = mod.get("coexist_workshop_variant")
                    workshop_variant_meta = {}
                    if isinstance(workshop_variant, dict) and workshop_variant:
                        workshop_variant_meta = {
                            "package_id_raw": workshop_variant.get("package_id_raw") or workshop_variant.get("package_id") or package_id,
                            "name": workshop_variant.get("name") or workshop_variant.get("display_name") or workshop_variant.get("alias_name") or package_id,
                            "alias_name": workshop_variant.get("alias_name") or workshop_variant.get("display_name") or workshop_variant.get("name") or package_id,
                            "workshop_id": self._normalize_workshop_id(workshop_variant.get("workshop_id")),
                            "source_url": self._normalize_source_url(workshop_variant.get("url")),
                        }
                    visible_map[package_id] = {
                        "package_id_raw": mod.get("package_id_raw") or mod.get("package_id") or package_id,
                        "name": mod.get("name") or package_id,
                        "alias_name": mod.get("alias_name") or mod.get("display_name") or mod.get("name") or package_id,
                        "workshop_id": self._normalize_workshop_id(mod.get("workshop_id")),
                        "source_url": self._normalize_source_url(mod.get("url")),
                        # 仅当当前环境里仍然存在可切换的 workshop 共存副本时，才继续保留 `_steam` token。
                        "has_coexist_workshop_variant": bool(workshop_variant_meta),
                        "coexist_workshop_variant": workshop_variant_meta,
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
            base_visible_meta = visible_map.get(package_id, {})
            token_info = parse_package_token(entry.get("package_token_raw") or entry.get("package_token") or package_id)
            visible_meta = base_visible_meta
            if token_info.source_preference == "steam":
                visible_meta = base_visible_meta.get("coexist_workshop_variant") or base_visible_meta
            asset_meta = asset_map.get(package_id, {})
            workshop_meta = meta_map.get(package_id, {})

            entry["package_id_raw"] = (
                (visible_meta.get("package_id_raw") if token_info.source_preference == "steam" else None)
                or entry.get("package_id_raw")
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

            if (
                token_info.source_preference == "steam"
                and package_id in visible_map
                and not base_visible_meta.get("has_coexist_workshop_variant")
            ):
                # stale `_steam` 只在 workshop 共存副本实际可用时才保留；
                # 否则回落到裸包名，避免前端显示本地版但保存时仍写回 `_steam`。
                entry["package_token"] = entry.get("package_id") or token_info.canonical_package_id or ""

        return entries

    def _build_entries_from_parsed(self, parsed: ParsedLoadOrderData):
        """
        把纯解析结果转成当前项目内部使用的结构化 mod 条目。

        `backend.load_order` 不依赖数据库，也不关心当前 profile；
        这里才是“结合本项目上下文补全信息”的地方。
        """
        mods = self._enrich_mod_entries(
            self._build_mod_entries(
                parsed.package_ids,
                parsed.package_tokens,
                parsed.mod_names,
                parsed.workshop_ids,
                parsed.source_urls,
            )
        )
        return {
            "format": parsed.format,
            "list_name": parsed.list_name,
            "mods": mods,
            # active list 需要保留来源 token，便于前端继续持久化 workshop 版本选择。
            "active_mods": [entry.get("package_token") or entry["package_id"] for entry in mods],
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

    def _build_export_entries(
        self,
        active_ids,
        export_format: str = EXPORT_FORMAT_MODSCONFIG,
        *,
        preserve_package_tokens: bool = True,
    ):
        # 导出前统一生成结构化条目，避免两个导出分支重复查库和补名。
        normalized_ids = []
        normalized_tokens = []
        seen_ids = set()
        for package_token in active_ids or []:
            token_info = parse_package_token(package_token)
            package_id = normalize_companion_package_id(token_info.canonical_package_id)
            if not package_id or package_id in seen_ids:
                continue
            seen_ids.add(package_id)
            normalized_ids.append(package_id)
            normalized_tokens.append(
                token_info.normalized_token
                if token_info.source_preference == "steam" and package_id != CURRENT_COMPANION_PACKAGE_ID
                else package_id
            )

        entries = self._enrich_mod_entries(self._build_mod_entries(normalized_ids, normalized_tokens))
        for entry in entries:
            # 来源后缀是共存模组的实例选择信息，不能因导出格式不同而丢失。
            # 只有调用方明确要求“原始包名”时，才回落到不带后缀的规范包名。
            entry["export_package_id"] = (
                entry.get("package_token") or entry.get("package_id")
                if preserve_package_tokens
                else entry.get("package_id")
            )
        return entries

    def _build_active_ids_hash(self, active_ids: list[str] | None = None) -> str:
        normalized_ids = []
        for package_id in (active_ids or []):
            token_info = parse_package_token(package_id)
            if token_info.normalized_token:
                normalized_ids.append(token_info.normalized_token)
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
        if not expected: return False, current
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
            package_id = entry.get("export_package_id") or entry.get("package_token") or entry.get("package_id_raw") or entry.get("package_id")
            etree.SubElement(mod_ids_node, "li").text = package_id
            etree.SubElement(mod_names_node, "li").text = entry.get("name") or package_id
            etree.SubElement(workshop_ids_node, "li").text = entry.get("workshop_id") or "0"

        tree = etree.ElementTree(root)
        self._write_xml_tree_atomically(tree, write_path)

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
            package_id = entry.get("export_package_id") or entry.get("package_token") or entry.get("package_id_raw") or entry.get("package_id") or ""
            display_name = entry.get("name") or package_id
            workshop_id = entry.get("workshop_id") or "0"

            etree.SubElement(mod_ids_node, "li").text = package_id
            etree.SubElement(mod_steam_ids_node, "li").text = workshop_id
            etree.SubElement(mod_names_node, "li").text = display_name
            etree.SubElement(ids_node, "li").text = package_id
            etree.SubElement(names_node, "li").text = display_name

        tree = etree.ElementTree(root)
        self._write_xml_tree_atomically(tree, write_path)

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
            logger.warning(f"未找到 ModsConfig.xml：{mods_config_file_path}")
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
            error_message = tr("errors.load_order.parse_failed", "排序文件解析失败，请检查文件格式是否正确。")
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
                "errors": [str(error_message)],
                "message_key": error_message.message_key,
                "message_params": error_message.message_params,
                'import_check': {"summary": {}, "items": []},
                'version_token': self._build_version_token(mods_config_file_path, [], modify_time=modify_time),
            }

    def _build_empty_modsconfig_tree(self, current_version: str):
        root = etree.Element("ModsConfigData")
        ver = etree.SubElement(root, "version")
        ver.text = current_version
        etree.SubElement(root, "activeMods")
        etree.SubElement(root, "knownExpansions")
        return etree.ElementTree(root)

    def _backup_broken_modsconfig(self, source_path: str):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # 同一秒重复触发时直接覆盖同名备份。
        dest_path = os.path.join(self.other_dir, f"ModsConfig_broken_{timestamp}.xml")
        try:
            shutil.copy2(source_path, dest_path)
            logger.warning(
                f"已备份损坏的 ModsConfig.xml：profile_id={self.context.profile_id}, "
                f"path={dest_path}"
            )
            return True
        except Exception as backup_error:
            self._record_backup_error(
                f"备份损坏的 ModsConfig.xml 失败：profile_id={self.context.profile_id}, "
                f"source={source_path}, error={backup_error}"
            )
            return False

    def _load_modsconfig_tree_for_save(self, current_version: str):
        parser = etree.XMLParser(remove_blank_text=True)
        source_path = self.context.mods_config_file
        if not os.path.exists(source_path):
            return self._build_empty_modsconfig_tree(current_version)
        try:
            return etree.parse(source_path, parser)
        except Exception as e:
            try:
                self._backup_broken_modsconfig(source_path)
            except Exception as backup_error:
                self._record_backup_error(
                    f"备份损坏的 ModsConfig.xml 失败：profile_id={self.context.profile_id}, "
                    f"source={source_path}, error={backup_error}"
                )
            logger.warning(f"ModsConfig.xml 无法解析，保存时将重建并覆盖: {source_path}, error={e}")
            return self._build_empty_modsconfig_tree(current_version)

    def _write_xml_tree_atomically(self, tree, write_path: str):
        parent_dir = os.path.dirname(write_path) or "."
        os.makedirs(parent_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{Path(write_path).stem}_",
            suffix=f"{Path(write_path).suffix}.tmp",
            dir=parent_dir,
        )
        os.close(fd)
        try:
            tree.write(temp_path, pretty_print=True, xml_declaration=True, encoding="utf-8")
            os.replace(temp_path, write_path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            raise

    def save_active_mods(self, *args, **kwargs):
        """在同一把锁内完成保存、备份和轮换，避免并发操作同一个文件。"""
        with _BACKUP_LOCK:
            return self._save_active_mods(*args, **kwargs)

    def _save_active_mods(
        self,
        active_ids,
        target_path=None,
        trigger_dialog=False,
        is_dirty=True,
        export_format: str = EXPORT_FORMAT_MODSCONFIG,
        list_name: str | None = None,
        preserve_package_tokens: bool = True,
    ):
        """
        保存加载顺序。
        :param active_ids: Mod ID 列表
        :param target_path: 指定保存路径（绝对路径）。如果不传，默认覆盖游戏配置。
        :param trigger_dialog: 是否触发系统弹窗让用户选择保存位置。
        :param export_format: 导出格式，支持 ModsConfig.xml / ModList.xml / RML
        :param list_name: 导出 ModList.xml 时写入的 Name
        :param preserve_package_tokens: 是否保留 `_steam` 等来源后缀；自动保存和自动备份默认保留。
        """
        self.last_backup_error = ""
        export_format = str(export_format or EXPORT_FORMAT_MODSCONFIG).strip().lower()
        if export_format not in {EXPORT_FORMAT_MODSCONFIG, EXPORT_FORMAT_MODLIST, EXPORT_FORMAT_RML}:
            raise ValueError(f"不支持的导出格式: {export_format}")
        # 先统一整理一份可导出的结构化条目，避免不同导出分支重复查库补名。
        entries = self._build_export_entries(
            active_ids,
            export_format=export_format,
            preserve_package_tokens=preserve_package_tokens,
        )
        final_ids = [
            entry.get("export_package_id") or entry.get("package_id") or ""
            for entry in entries
        ]
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
        is_main_config_save = (
            export_format == EXPORT_FORMAT_MODSCONFIG
            and write_path == self.context.mods_config_file
        )
        if is_main_config_save and is_dirty:
            # 自动备份失败只影响备份提示，不阻止用户当前这次排序保存。
            try:
                self._create_backup()
            except Exception as backup_error:
                self._record_backup_error(
                    f"创建自动备份失败：profile_id={self.context.profile_id}, "
                    f"source={self.context.mods_config_file}, error={backup_error}"
                )
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
                # 尝试保留原有的 knownExpansions 等信息；旧文件坏掉时直接重建后覆盖。
                tree = self._load_modsconfig_tree_for_save(current_version)
                root = tree.getroot()
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
                # 4. 用临时文件原子替换，避免中途失败留下空文件。
                self._write_xml_tree_atomically(tree, write_path)
                # 同步一份最近备份，改用 RML 格式，方便后续完整恢复和识别。
                latest_path = os.path.join(self.backup_root, "Latest_ModList.rml")
                try:
                    self._write_rml_file(latest_path, entries)
                except Exception as latest_error:
                    # Latest 是辅助副本，失败只提示备份异常，不能把排序文件保存结果改成失败。
                    self._record_backup_error(
                        f"更新最近备份失败，排序文件已保存：profile_id={self.context.profile_id}, "
                        f"path={latest_path}, error={latest_error}"
                    )
                logger.info(f"成功保存 {len(active_ids)} 个模组到: {write_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存排序文件时出错：{e}")
            raise Exception(f"保存排序文件时出错：{e}")

    def _record_backup_error(self, message: str):
        self.last_backup_error = message
        logger.error(message)

    @staticmethod
    def _backup_files(directory: str) -> list[Path]:
        root = Path(directory)
        return sorted(
            (
                item for item in root.iterdir()
                if item.is_file() and not item.is_symlink() and item.suffix.lower() in _BACKUP_FILE_SUFFIXES
            ),
            key=lambda item: item.name.lower(),
        )

    def _backup_created_at(self, path: Path) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime)

    def _verify_backup_readable(self, path: str):
        with open(path, "rb") as handle:
            handle.read(1)
        parsed = parse_load_order_file(path)
        if parsed.errors:
            raise ValueError("备份文件解析失败：" + "; ".join(parsed.errors))

    def _create_backup(self):
        """
        [核心重构] 备份当前磁盘上的旧状态：
        1. 读取磁盘上现有的 ModsConfig.xml。
        2. 解析并利用数据库补全元数据（Name, WorkshopID）。
        3. 以 RML 格式存入备份目录。
        """
        old_file_path = self.context.mods_config_file
        if not old_file_path or not os.path.isfile(old_file_path):
            return False
        with _BACKUP_LOCK:
            dest_path = ""
            try:
                old_data = self.read_active_mods(old_file_path)
                errors = list(old_data.get("errors") or [])
                if errors:
                    raise ValueError("旧 ModsConfig.xml 解析失败：" + "; ".join(map(str, errors)))
                if not old_data.get("mods") and not old_data.get("active_mods"):
                    return False

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                # 自动备份同名时覆盖最新快照。
                dest_path = os.path.join(self.today_dir, f"ModList_{timestamp}.rml")
                self._write_rml_file(dest_path, old_data.get("mods", []) or [])
                self._verify_backup_readable(dest_path)
                logger.info(
                    f"已创建自动备份：profile_id={self.context.profile_id}, path={dest_path}"
                )
                return True
            except Exception as backup_error:
                self._record_backup_error(
                    f"创建自动备份失败：profile_id={self.context.profile_id}, "
                    f"source={old_file_path}, path={dest_path or self.today_dir}, error={backup_error}"
                )
                return False

    def _remove_backup_file(self, path: Path) -> bool:
        try:
            path.unlink()
            logger.info(
                f"已清理自动备份：profile_id={self.context.profile_id}, path={path}"
            )
            return True
        except Exception as error:
            logger.error(
                f"清理自动备份失败：profile_id={self.context.profile_id}, path={path}, error={error}"
            )
            return False

    def _archive_backup_file(self, path: Path, created_at: datetime.datetime) -> bool:
        """把一个到期短期备份并入同日长期备份，并保留较新的快照。"""
        try:
            earlier_files = self._backup_files(self.earlier_dir)
            same_day = []
            for item in earlier_files:
                try:
                    item_time = self._backup_created_at(item)
                except OSError as error:
                    logger.error(
                        f"读取长期备份时间失败：profile_id={self.context.profile_id}, "
                        f"path={item}, error={error}"
                    )
                    continue
                if item_time.date() == created_at.date():
                    same_day.append((item, item_time))

            target = Path(self.earlier_dir) / path.name
            os.replace(path, target)
            logger.info(
                f"已转存自动备份：profile_id={self.context.profile_id}, "
                f"source={path}, target={target}"
            )
            result = True
            for existing_path, _existing_time in same_day:
                if existing_path != target:
                    result = self._remove_backup_file(existing_path) and result
            return result
        except Exception as error:
            logger.error(
                f"转存自动备份失败：profile_id={self.context.profile_id}, path={path}, error={error}"
            )
            return False

    def _rotate_backups(self, now: datetime.datetime | None = None):
        """
        备份轮换策略：
        - today 文件夹只保留"今天"的文件，过期的移入 earlier。
        - earlier 文件夹里，每一天只保留最后一份备份。
        - 清理超过 retention_days 的备份。
        """
        current_time = now or datetime.datetime.now()
        rotation_ok = True
        with _BACKUP_LOCK:
            files_by_date: dict[datetime.date, list[tuple[Path, datetime.datetime]]] = {}
            try:
                today_files = self._backup_files(self.today_dir)
            except OSError as error:
                logger.error(
                    f"读取短期备份目录失败：profile_id={self.context.profile_id}, "
                    f"path={self.today_dir}, error={error}"
                )
                return False

            for path in today_files:
                try:
                    created_at = self._backup_created_at(path)
                except OSError as error:
                    rotation_ok = False
                    logger.error(
                        f"读取短期备份时间失败：profile_id={self.context.profile_id}, "
                        f"path={path}, error={error}"
                    )
                    continue
                if created_at.date() >= current_time.date():
                    continue
                if current_time - created_at < datetime.timedelta(hours=_BACKUP_PROTECTION_HOURS):
                    continue
                files_by_date.setdefault(created_at.date(), []).append((path, created_at))

            for _date, candidates in files_by_date.items():
                candidates.sort(key=lambda item: item[1])
                for stale_path, _stale_time in candidates[:-1]:
                    rotation_ok = self._remove_backup_file(stale_path) and rotation_ok
                candidate_path, candidate_time = candidates[-1]
                rotation_ok = self._archive_backup_file(candidate_path, candidate_time) and rotation_ok

            try:
                earlier_files = self._backup_files(self.earlier_dir)
            except OSError as error:
                logger.error(
                    f"读取长期备份目录失败：profile_id={self.context.profile_id}, "
                    f"path={self.earlier_dir}, error={error}"
                )
                return False

            earlier_by_date: dict[datetime.date, list[tuple[Path, datetime.datetime]]] = {}
            for path in earlier_files:
                try:
                    created_at = self._backup_created_at(path)
                except OSError as error:
                    rotation_ok = False
                    logger.error(
                        f"读取长期备份时间失败：profile_id={self.context.profile_id}, "
                        f"path={path}, error={error}"
                    )
                    continue
                earlier_by_date.setdefault(created_at.date(), []).append((path, created_at))

            for _date, files in earlier_by_date.items():
                files.sort(key=lambda item: item[1], reverse=True)
                for stale_path, _stale_time in files[1:]:
                    rotation_ok = self._remove_backup_file(stale_path) and rotation_ok

            try:
                retention_days = max(0, int(settings.config.backup_retention_days or 0))
            except (TypeError, ValueError) as error:
                logger.error(
                    f"备份保留天数配置无效：profile_id={self.context.profile_id}, "
                    f"value={settings.config.backup_retention_days}, error={error}"
                )
                return False
            cutoff_date = current_time.date() - datetime.timedelta(days=retention_days)
            try:
                retained_files = self._backup_files(self.earlier_dir)
            except OSError as error:
                logger.error(
                    f"读取长期备份目录失败：profile_id={self.context.profile_id}, "
                    f"path={self.earlier_dir}, error={error}"
                )
                return False
            for path in retained_files:
                try:
                    if self._backup_created_at(path).date() < cutoff_date:
                        rotation_ok = self._remove_backup_file(path) and rotation_ok
                except OSError as error:
                    rotation_ok = False
                    logger.error(
                        f"读取长期备份时间失败：profile_id={self.context.profile_id}, "
                        f"path={path}, error={error}"
                    )
        return rotation_ok

    def get_all_backups(self):
        """获取所有备份文件路径"""
        with _BACKUP_LOCK:
            today_files = self._backup_files(self.today_dir)
            earlier_files = self._backup_files(self.earlier_dir)
            other_files = self._backup_files(self.other_dir)
        last_backup_file = Path(self.backup_root) / "Latest_ModList.rml"
        if not last_backup_file.is_file():
            last_backup_file = ''
        
        def build_items(files):
            items = []
            for raw_path in files:
                path = Path(raw_path)
                try:
                    items.append({
                        'path': str(path),
                        'modify_time': int(path.stat().st_mtime * 1000),
                        'source_profile_id': self.context.profile_id,
                    })
                except OSError as error:
                    logger.error(
                        f"读取备份信息失败：profile_id={self.context.profile_id}, "
                        f"path={path}, error={error}"
                    )
            return items
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
