import asyncio
import base64
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import gc
import json
import os
import sys
import threading
import time
import functools
import uuid
import webbrowser
import webview
import tempfile
from pathlib import Path
from dataclasses import dataclass, asdict, is_dataclass
from types import SimpleNamespace
from typing import Any, Dict, List
from peewee import Model, JOIN
from playhouse.shortcuts import model_to_dict

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[1]
    # 调试打印，确保路径正确
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

# 1. 引入配置管理
from backend.managers.mgr_steamcmd_core import SteamCMDController
from backend.settings import DATA_DIR, HOME_DIR, TOOL_MODS_DIR, settings, RULES_DIR
from backend.utils.event_bus import EventBus
from backend._version import __version__, __build__, get_all_changelogs
from backend.utils.tools import normalize_package_id
from backend.utils.tools import current_ms, generate_path_hash
from backend.utils.logger import logger, app_log_reader
from backend.managers.mgr_network import network_mgr

# 2. 引入数据库层
from backend.database.models import ModAsset, ModInterlock, UserModData, GithubModRecord, GithubTimeline, db
from backend.database.dao import CollectionDAO, GroupDAO, ModDAO, ModInterlockDAO, ModMaintenanceDAO
from backend.database.dao_ext import ExtDAO
from backend.database.runtime import close_db, clear_db, init_db
from backend.database.repair import (
    _cleanup_database_sidecars,
    _cleanup_repair_artifacts,
    _remove_file_with_retry,
    prepare_database_for_startup,
    prepare_manual_database_repair,
)

# 3. 引入业务逻辑管理器
from backend.scanner.parser_dlc import DLCParser
from backend.scanner.mod_scanner import ModScanner
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_game_install import GameInstallInspector
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_files import FileManager, file_mgr, PathChecker
from backend.managers.mgr_game_logs import GameLogManager, LogCondenser
from backend.managers.mgr_sorter import OrderSorter
from backend.managers.mgr_download import DownloadManager, TaskStatus
from backend.managers.mgr_steam import RIMWORLD_APP_ID, SteamManager
from backend.managers.mgr_sub_browser import SubBrowserManager
from backend.ai.ai_service import AIManager
from backend.managers.mgr_workshop_db import WorkshopDBManager
# from backend.managers.mgr_workshop_db_old import WorkshopDBManager
from backend.managers.mgr_update import UpdateManager, UpdateInfo
from backend.managers.mgr_game_monitor import GameMonitor
from backend.managers.mgr_profile import ProfileContext, ProfileManager
from backend.managers.mgr_mod_config import ModConfigManager
from backend.utils.profile_runtime import resolve_profile_runtime_capabilities
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.managers.mgr_github import GithubManager
from backend.managers.mgr_maintenance import MaintenanceManager
from backend.managers.mgr_data_bundle import DataBundleManager
from backend.managers.mgr_mod_package import ModPackageManager
from backend.managers.mgr_texture_opt import TextureOptCancelled, TextureOptimizationManager
from backend.load_order.language_pack_ownership import resolve_language_pack_ownership_for_mods
from backend.load_order.package_tokens import parse_package_token
from backend.browser_runtime import build_sub_browser_target_url
from backend.utils.restart import launch_new_application
from backend.migrations.app_upgrade import normalize_duplicate_group_names_on_load, run_app_upgrade_migrations
from backend.text_search.manager import FileSearchManager

GITHUB_SUBS_REFRESH_MIN_INTERVAL_MS = 3 * 60 * 1000


def _ensure_bundle_filename_extension(filename: str, preferred_extension: str, accepted_extensions: list[str] | tuple[str, ...]) -> str:
    normalized = str(filename or "").strip()
    lowered = normalized.lower()
    for extension in accepted_extensions:
        if lowered.endswith(str(extension or "").lower()):
            return normalized
    return f"{normalized}{preferred_extension}"


def _build_dialog_file_type_label(label: str, extensions: list[str] | tuple[str, ...]) -> str:
    normalized_extensions = [
        f"*{str(extension or '').strip()}"
        for extension in extensions
        if str(extension or "").strip()
    ]
    return f"{label} ({';'.join(normalized_extensions)})" if normalized_extensions else f"{label} (*.*)"


def log_api_call(func):
    """ 
    装饰器：记录 API 调用、参数及耗时 
    仅在 DEBUG 模式或发生错误时记录详细信息
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        # 截断过长的参数显示（如巨大的文件内容）
        safe_args = [str(a)[:50] + '...' if len(str(a)) > 50 else a for a in args]
        try:
            EventBus.resume() # 在执行操作前恢复事件总线
            # 执行原函数
            result = func(self, *args, **kwargs)
            duration = (time.time() - start_time) * 1000
            # 只有慢请求或显式 Debug 才记录 INFO，否则记录 DEBUG 避免刷屏
            if duration > 500: 
                logger.warning(f"API [SLOW] {func_name} took {duration:.2f}ms")
            else:
                logger.debug(f"API {func_name}({safe_args}) took {duration:.2f}ms")
            return result
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"API {func_name} failed after {duration:.2f}ms: {str(e)}", exc_info=True)
            # 这里的异常通常需要返回给前端一个标准格式
            return ApiResponse.error(f"System Error: {str(e)}")
            
    return wrapper



@dataclass
class ApiResponse:
    """
    统一 API 响应格式
    """
    status: str = "success"  # "success" | "error"
    message: str = ""        # 提示信息 (用于前端 Toast)
    data: Any = None         # 数据载体 (可以是 dict, list, None)

    @classmethod
    def success(cls, data=None, message=""):
        # logger.debug(f"API Success: {message}, data={cls.serialize_data(data)}")
        return asdict(cls(status="success", data=cls.serialize_data(data), message=message))

    @classmethod
    def error(cls, message, data=None):
        has_exc = sys.exc_info()[0] is not None
        logger.error( f"API Error: {message}", exc_info=has_exc, stacklevel=2)
        return asdict(cls(status="error", message=message, data=cls.serialize_data(data)))
    
    @classmethod
    def warning(cls, message, data=None):
        logger.warning(f"API Warning: {message}", stacklevel=2)
        return asdict(cls(status="warning", message=message, data=cls.serialize_data(data)))

    @classmethod
    def serialize_data(cls, obj):
        if obj is None: return None
        """递归将模型和日期转换为 JSON 可接受的类型"""
        # 1. 检查对象是否自带 to_dict 方法 (这会覆盖 dataclass 的默认行为)
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
            return cls.serialize_data(obj.to_dict())
        # 2. 如果是 dataclass 但没有 to_dict，再回退到默认的 asdict
        if is_dataclass(obj):
            from dataclasses import asdict
            return cls.serialize_data(asdict(obj)) # type: ignore
        # 1. 处理 Peewee 模型对象
        if isinstance(obj, Model):
            # recurse=True 自动处理关联表，但通常建议只转单表
            return cls.serialize_data(model_to_dict(obj))
        # 2. 处理日期和时间
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()  # 转为 "2023-10-27T10:00:00" 这种前端好处理的格式
        # 3. 处理集合、元组 (转为 List)
        if isinstance(obj, (set, tuple, frozenset)):
            return [cls.serialize_data(i) for i in obj]
        # 4. 处理列表 (递归转换列表内部的元素)
        if isinstance(obj, list):
            return [cls.serialize_data(i) for i in obj]
        # 5. 处理字典 (递归转换 Key 和 Value)
        if isinstance(obj, dict):
            # 注意：JSON 的 Key 必须是字符串
            return {str(k): cls.serialize_data(v) for k, v in obj.items()}
        # 6. 处理其他常用类型
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj) # 或者 str(obj) 取决于精度要求
        if isinstance(obj, Enum):
            return obj.value
        # 7. 基本类型 (int, float, str, bool, None) 直接返回
        return obj


class LaunchWarningAction(Enum):
    CONTINUE = "continue"
    CLEAR_WORKSHOP = "clear_workshop"
    WAIT_STEAM_EXIT = "wait_steam_exit"
    CANCEL = "cancel"


class API:
    """
    暴露给 pywebview 前端的统一接口类。
    所有前端调用的 window.pywebview.api.xxx 方法都在这里定义。
    """

    def __init__(self, runtime_mode: str = "desktop"):
        logger.info("API Layer Initializing...")
        self._window = None  # 私有属性
        self._runtime_mode = str(runtime_mode or "desktop").strip().lower() or "desktop"
        self._upgrade_context = {
            "version_changed": False,
            "old_version": "0.0.0",
            "new_version": __version__,
            "actions_taken": [],      # 记录后端已经静默完成的操作
            "pending_actions": [],    # 记录需要前端配合的操作 (如 'show_news', 'force_scan')
            "messages": []            # 具体的提示文本
        }
        # 1. 初始化数据库
        # 数据库文件放在当前工作目录的 data 目录下。
        # 启动前先跑一遍数据库预处理：应用待切换修复库、尝试被动热修复、必要时降级为空库继续启动。
        db_path = str(DATA_DIR / 'mod_manager.db')
        startup_repair_result = prepare_database_for_startup(db_path)
        self.is_first_db_init = bool(startup_repair_result.get('created_clean_database')) or (not os.path.exists(db_path))
        init_ok = init_db(db_path)
        if not init_ok:
            self._upgrade_context["messages"].append("数据库加载失败，部分功能可能暂时不可用。")
        self._upgrade_context["actions_taken"].extend(startup_repair_result.get("actions_taken", []))
        self._upgrade_context["messages"].extend(startup_repair_result.get("messages", []))
        self._native_drop_bound = False
        self._native_drop_selector = '#backup-drop-zone'
        self._native_drop_element = None
        self._native_drop_handler = None
        self._browser_base_url = ""
        self._browser_import_files: set[str] = set()
        self._db_maintenance_lock = threading.Lock()
        self._db_background_task_lock = threading.Lock()
        self._db_background_tasks: dict[str, threading.Event] = {}
        self._db_maintenance_requested = threading.Event()
        self._github_subs_refresh_lock = threading.Lock()
        self._github_subs_refresh_running = False
        self._github_subs_refresh_started_at = 0
        self._runtime_link_sync_state: dict[str, dict[str, Any]] = {}
        self._last_runtime_link_sync_result: dict[str, Any] = {}
        # 桌面模式首屏阶段只允许触发一次后台预热，避免 loaded / ready 多次回调时重复导入大缓存文件。
        self._startup_warmup_started = False
        # 应用层升级迁移必须早于外置缓存库管理器初始化。
        # 否则像 workshop_cache.db 这类需要“删库重建”的迁移，
        # 会在 Windows 上撞到已打开文件句柄导致无法删除。
        self._handle_app_version_upgrade()
        renamed_groups = normalize_duplicate_group_names_on_load()
        if renamed_groups:
            self._upgrade_context["messages"].append(f"检测到重名分组，已自动重命名 {len(renamed_groups)} 项。")
            logger.warning(
                "Duplicate group names normalized on load: %s",
                ", ".join(f"{old_name!r}->{new_name!r}" for _, old_name, new_name in renamed_groups),
            )
        # 2. 实例化各个管理器
        self.workshop_db_mgr = WorkshopDBManager()
        self.game_mgr = GameManager()
        self.profile_mgr = ProfileManager()
        self.active_context = None
        self.load_order_mgr = None
        self.game_log_mgr = None
        self.scanner = None
        self.sorter = None
        # 3. 启动时激活上下文
        self._bootstrap_context(settings.config.current_profile_id)
        self.game_monitor = GameMonitor(self)
        self.download_mgr = DownloadManager()
        self.github_mgr = GithubManager()
        self.file_mgr = file_mgr
        self.steam_mgr = SteamManager()
        self.ai_mgr = AIManager()
        self.data_bundle_mgr = DataBundleManager(
            self.profile_mgr,
            self.ai_mgr,
            rule_mgr_provider=lambda: self.sorter.rule_mgr if self.sorter else None,
        )
        self.mod_package_mgr = ModPackageManager(
            self.profile_mgr,
            data_bundle_mgr=self.data_bundle_mgr,
            load_order_mgr_provider=lambda: self.load_order_mgr,
            rule_mgr_provider=lambda: self.sorter.rule_mgr if self.sorter else None,
        )
        self.browser_window = SubBrowserManager(self)
        self.update_mgr = UpdateManager()
        self.texture_mgr = TextureOptimizationManager()
        self.file_search_mgr = FileSearchManager(self)
        self.maintenance_mgr = MaintenanceManager(
            self.steam_mgr,
            self.texture_mgr,
            self.workshop_db_mgr,
            rule_mgr_provider=lambda: self.sorter.rule_mgr if self.sorter else None,
        )
        
        # 每次启动 API 时，强制检查并修复 SteamCMD 的软链接！
        if settings.config.self_mods_path and settings.config.steamcmd_mods_path:
            FileManager.sync_steamcmd_root_link()
        # 打包版每次启动都校验 Browser mode 快捷方式，缺失或过期就自动修复。
        if self._runtime_mode == "desktop" and os.name == "nt":
            self._ensure_browser_mode_shortcut()

        logger.info("API Layer Ready.")
        
    @staticmethod
    def _normalize_str_items(items: List[str] | str) -> list[str]:
        if isinstance(items, str):
            value = items.strip()
            return [value] if value else []
        return [str(item or '').strip() for item in items if str(item or '').strip()]

    @staticmethod
    def _build_delete_response(target_name: str, total: int, result: dict, success_message: str = ""):
        success_count = int(result.get('success_count', 0) or 0)
        errors = [str(item) for item in (result.get('errors') or []) if str(item).strip()]

        if total <= 0:
            return ApiResponse.warning(f"未提供需要删除的{target_name}", data=result)
        if success_count <= 0 and errors:
            return ApiResponse.error("\n".join(errors), data=result)
        if success_count != total:
            return ApiResponse.warning(f"部分{target_name}删除失败：{total-success_count} 项未成功删除", data=result)
        return ApiResponse.success(data=result, message=success_message)

    def _delete_paths(self, paths: List[str] | str, force: bool = False) -> dict:
        normalized_paths = self._normalize_str_items(paths)
        success_count, error_list = file_mgr.delete_paths(normalized_paths, force=force)
        return {
            'success_count': success_count,
            'errors': error_list,
            'force': bool(force),
            'paths': normalized_paths,
        }

    def _resolve_profile_runtime_caps_from_profile(self, profile) -> dict[str, Any]:
        # API 经常只拿到数据库 Profile，而不是完整 ProfileContext。
        # 这里单独补一层轻量解析，把持久化的 `is_steam` 和动态的
        # `is_steam_managed` 拼成统一事实，再交给运行能力解析层。
        install_facts = GameInstallInspector().quick_inspect(getattr(profile, 'game_install_path', ''))
        profile_state = SimpleNamespace(
            is_steam=bool(getattr(profile, 'is_steam', False)),
            is_steam_managed=bool(getattr(profile, 'is_steam_managed', install_facts.is_steam_managed)),
            prefer_steam_launch=getattr(profile, 'prefer_steam_launch', False),
            use_workshop_mods=getattr(profile, 'use_workshop_mods', False),
        )
        return resolve_profile_runtime_capabilities(profile_state)

    @staticmethod
    def _collect_overwritten_profile_ids(import_result: dict[str, Any] | None) -> set[str]:
        return {
            str(profile.get("profile_id") or "").strip()
            for profile in ((import_result or {}).get("profiles") or [])
            if str(profile.get("mode") or "").strip().lower() == "overwrite"
        }

    def _reload_current_profile_after_import(self, import_result: dict[str, Any] | None) -> bool:
        current_profile_id = str(settings.config.current_profile_id or "").strip()
        if not current_profile_id:
            return False
        if current_profile_id not in self._collect_overwritten_profile_ids(import_result):
            return False
        self._bootstrap_context(current_profile_id)
        return True
    
    
    def _bootstrap_context(self, profile_id: str):
        """装载当前环境，并重建所有业务引擎"""
        # 在重建前，先停止旧的监视器
        if self.game_log_mgr: self.game_log_mgr.stop_realtime_monitor()
        old_scanner = getattr(self, 'scanner', None)
        if old_scanner:
            old_scanner.stop_scan()
            if not old_scanner.wait_until_idle(timeout=2.0):
                logger.warning("旧扫描器未在切换环境前及时退出，继续重建上下文。")
        
        try:
            # 获取上下文
            self.active_context = self.profile_mgr.activate_profile(profile_id)
        except Exception as e:
            # 兜底：如果报错，强制退回 default
            logger.error(f"Bootstrap profile {profile_id} failed: {str(e)}", exc_info=True)
            self.active_context = self.profile_mgr.activate_profile('default')
        
        # 【拦截分流】如果环境不健康，不再实例化底层的业务引擎！
        if not self.active_context.is_healthy:
            logger.warning(f"环境 {profile_id} 路径失效，进入锁定模式！")
            self.load_order_mgr = None
            self.scanner = None
            self.game_log_mgr = None
            self.sorter = None
            return # 提早退出，阻止系统继续加载 Mod 数据

        # 确保 self_mods_path 目录存在
        self_mods_path = str(settings.config.self_mods_path or "").strip()
        if self_mods_path:
            os.makedirs(self_mods_path, exist_ok=True)
        else:
            logger.warning("self_mods_path 为空，跳过管理器 Mod 目录创建。")
        
        # 依赖注入：将上下文发给所有的 Manager
        self.scanner = ModScanner(
            self.active_context,
            runtime_link_sync_handler=self._sync_runtime_links_after_scan,
        )
        self.load_order_mgr = LoadOrderManager(self.active_context)
        self.game_log_mgr = GameLogManager(self.active_context)
        self.sorter = OrderSorter(self.active_context)
        # 启动新的实时监视器
        if self.game_log_mgr: self.game_log_mgr.start_realtime_monitor()

    def _ensure_browser_mode_shortcut(self):
        """仅在打包桌面模式下确保 Browser mode 快捷方式存在。"""
        try:
            import sys
            if not getattr(sys, 'frozen', False): return

            result = FileManager.ensure_browser_mode_shortcut(sys.executable)
            action = "已创建" if result.get('changed') else "已存在"
            shortcut_path = result.get('shortcut', {}).get('shortcut_path', '')
            logger.info(f"Browser mode 快捷方式{action}: {shortcut_path}")
        except Exception as e:
            # 快捷方式自修复失败不应阻塞主程序启动，只记录日志即可。
            logger.warning(f"Browser mode 快捷方式校验失败: {e}", exc_info=True)

    def _resolve_load_order_scope(self, profile_id: str | None = None):
        """
        解析读取排序/备份时应使用的上下文。
        仅当读取当前激活环境时复用现有 manager；查看其它环境备份时只构造临时只读 manager。
        """
        target_profile_id = str(profile_id or "").strip()
        if not target_profile_id:
            target_profile_id = self.active_context.profile_id if self.active_context else settings.config.current_profile_id

        if self.active_context and self.load_order_mgr and target_profile_id == self.active_context.profile_id:
            profile = self.profile_mgr.get_current_profile()
            return self.active_context, profile

        context = self.profile_mgr.build_profile_context(target_profile_id)
        profile = self.profile_mgr.get_profile(target_profile_id)
        return context, profile

    def _handle_app_version_upgrade(self):
        """实例初始化时运行的升级逻辑"""
        from backend.database.models import SystemInfo
        last_ver_record = SystemInfo.get_or_none(SystemInfo.key == 'app_version')
        current_version = __version__
        if not last_ver_record:
            # 新库、重置库或修复后缺失元数据的库，不应被误判成跨版本升级。
            SystemInfo.insert(key='app_version', value=current_version).on_conflict_replace().execute()
            return

        last_version = str(last_ver_record.value or '').strip() or current_version
        if last_version == current_version: return

        # 标记版本已变动
        self._upgrade_context["version_changed"] = True
        self._upgrade_context["old_version"] = last_version
        self._upgrade_context["changelog"] = get_all_changelogs()

        # --- 执行具体的升级任务 ---
        try:
            migration_result = run_app_upgrade_migrations(
                last_version=last_version,
                current_version=current_version,
            )
            self._upgrade_context["pending_actions"].extend(migration_result.pending_actions)
            self._upgrade_context["messages"].extend(migration_result.messages)
            # --- 升级任务执行完毕，持久化新版本号 ---
            SystemInfo.insert(key='app_version', value=current_version).on_conflict_replace().execute()
            logger.info(f"应用升级处理完成: {last_version} -> {current_version}")

        except Exception as e:
            logger.error(f"Upgrade tasks failed: {e}", exc_info=True)
    
    @log_api_call
    def get_changelog(self):
        """主动获取全量更新日志数据"""
        from backend._version import get_all_changelogs
        return ApiResponse.success(get_all_changelogs())
    
    def cleanup(self):
        """关闭数据库清理资源"""
        for temp_path in list(self._browser_import_files):
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                logger.debug(f"Failed to clean browser temp import file: {temp_path}", exc_info=True)
            finally:
                self._browser_import_files.discard(temp_path)
        # 停止后台扫描任务 (如果有)
        if hasattr(self, 'scanner') and self.scanner: self.scanner.stop_scan() 
        # 停止游戏日志监视器
        if self.game_log_mgr: self.game_log_mgr.stop_realtime_monitor()
        # 停止游戏监控
        if self.game_monitor: self.game_monitor.running = False
        # 暂停所有事件发送
        EventBus.pause()
        if self.steam_mgr:
            self.steam_mgr.cleanup_runtime()
        logger.info("Closing database connection...")
        close_db()
        # SteamCMD 的生命周期已统一收敛到 SteamManager 内部，避免旧控制器残留双重管理。
        
    
    def set_window(self, window: webview.Window):
        """设置主窗口"""
        self._window  = window
        # 绑定 loaded 事件，确保窗口完全就绪后再启动监视器
        window.events.loaded += self._on_app_loaded
    
    def get_window(self):
        """获取主窗口"""
        return self._window

    def is_browser_runtime(self) -> bool:
        return self._runtime_mode == 'browser'

    def set_browser_base_url(self, base_url: str):
        self._browser_base_url = str(base_url or "").rstrip("/")

    def _build_load_order_result(
        self,
        file_path: str,
        res: dict | None = None,
        source_profile_id: str = "",
        source_profile_name: str = "",
        list_name_override: str = "",
    ):
        payload = dict(res or {})
        list_name = str(list_name_override or payload.get('list_name') or '').strip()
        return {
            "file": file_path,
            "active_ids": payload.get('active_mods', []),
            "modify_time": payload.get('modify_time', 0),
            "format": payload.get('format', 'modsconfig'),
            "list_name": list_name,
            "mods": payload.get('mods', []),
            "mod_names": payload.get('mod_names', []),
            "mod_steam_workshop_ids": payload.get('mod_steam_workshop_ids', []),
            "source_urls": payload.get('source_urls', []),
            "workshop_ids": payload.get('workshop_ids', []),
            "warnings": payload.get('warnings', []),
            "errors": payload.get('errors', []),
            "import_check": payload.get('import_check', {"summary": {}, "items": []}),
            "version_token": payload.get('version_token', {}),
            "source_profile_id": source_profile_id,
            "source_profile_name": source_profile_name if source_profile_id else '',
        }

    def _write_browser_import_temp_file(self, filename: str, content: bytes) -> str:
        suffix = Path(str(filename or "").strip() or "import.txt").suffix or ".txt"
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=suffix,
            prefix="rmm-import-",
            delete=False,
        ) as temp_file:
            temp_file.write(content or b"")
            temp_path = temp_file.name
        self._browser_import_files.add(temp_path)
        return temp_path

    def _decode_browser_import_payload(self, payload: Any):
        if isinstance(payload, dict):
            filename = str(payload.get("filename") or "import.txt").strip() or "import.txt"
            if payload.get("content_base64"):
                return filename, base64.b64decode(str(payload.get("content_base64") or ""))
            text_content = str(payload.get("content") or "")
            encoding = str(payload.get("encoding") or "utf-8") or "utf-8"
            return filename, text_content.encode(encoding, errors="replace")
        filename = "import.txt"
        return filename, str(payload or "").encode("utf-8")

    def _build_save_conflict_payload(self, disk_result: dict, editing_ids: list[str]):
        return {
            "status": "conflict",
            "disk_order": self._build_load_order_result(
                disk_result.get("source_path") or (self.active_context.mods_config_file if self.active_context else ""),
                disk_result,
            ),
            "editing_order": {
                "active_ids": self._normalize_load_order_tokens(editing_ids),
            },
        }

    @staticmethod
    def _normalize_load_order_token(package_id: str) -> str:
        token_info = parse_package_token(package_id)
        if not token_info.canonical_package_id:
            return ""
        return token_info.normalized_token if token_info.source_preference == "steam" else token_info.canonical_package_id

    @classmethod
    def _normalize_load_order_tokens(cls, package_ids: list[str] | None) -> list[str]:
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for package_id in package_ids or []:
            normalized = cls._normalize_load_order_token(str(package_id or ""))
            if not normalized or normalized in seen_ids:
                continue
            seen_ids.add(normalized)
            normalized_ids.append(normalized)
        return normalized_ids

    @classmethod
    def _canonicalize_load_order_ids(cls, package_ids: list[str] | None):
        canonical_ids: list[str] = []
        preferred_tokens: dict[str, str] = {}
        seen_ids: set[str] = set()
        for package_id in package_ids or []:
            token_info = parse_package_token(package_id)
            canonical = token_info.canonical_package_id
            if not canonical:
                continue
            normalized_token = cls._normalize_load_order_token(str(package_id or ""))
            preferred_tokens[canonical] = normalized_token or canonical
            if canonical in seen_ids:
                continue
            seen_ids.add(canonical)
            canonical_ids.append(canonical)
        return canonical_ids, preferred_tokens

    @staticmethod
    def _restore_load_order_tokens(package_ids: list[str], preferred_tokens: dict[str, str] | None = None) -> list[str]:
        result: list[str] = []
        seen_ids: set[str] = set()
        token_map = preferred_tokens or {}
        for package_id in package_ids or []:
            canonical = normalize_package_id(package_id)
            if not canonical:
                continue
            restored = str(token_map.get(canonical) or canonical).strip().lower()
            if not restored or restored in seen_ids:
                continue
            seen_ids.add(restored)
            result.append(restored)
        return result

    @staticmethod
    def _normalize_existing_dir(path_value: str | None) -> str:
        """
        统一把候选目录规整成文件选择器可用的初始目录。
        - 文件路径取其父目录
        - 不存在的路径返回空串，让上层继续走回退链
        """
        value = str(path_value or "").strip()
        if not value: return ""
        candidate = Path(value)
        # 保存对话框返回的目标文件在成功写入前通常还不存在，这里根据后缀推断父目录。
        if candidate.is_file() or candidate.suffix:
            candidate = candidate.parent
        return str(candidate) if candidate.exists() and candidate.is_dir() else ""

    @staticmethod
    def _ensure_directory(path_value: str | None) -> str:
        """
        确保目录存在并返回规范化后的目录字符串。
        若创建失败则返回空串，由上层继续走兜底逻辑。
        """
        value = str(path_value or "").strip()
        if not value: return ""
        try:
            candidate = Path(value)
            candidate.mkdir(parents=True, exist_ok=True)
            return str(candidate) if candidate.exists() and candidate.is_dir() else ""
        except Exception:
            logger.warning(f"无法创建目录: {value}", exc_info=True)
            return ""

    def _get_default_import_dir(self, context: ProfileContext | None) -> str:
        """
        默认导入目录固定指向当前环境用户数据下的 ModLists。
        该目录是用户显式要求的导入入口，目录缺失时自动创建。
        """
        if not context: return ""
        base_dir = str(Path(context.user_data_path) / "ModLists")
        return self._ensure_directory(base_dir)

    def _get_default_export_dir(self) -> str:
        """
        默认导出目录保持现有行为，继续使用当前环境备份区下的 other 目录。
        """
        if self.load_order_mgr and getattr(self.load_order_mgr, "other_dir", ""):
            return self._ensure_directory(self.load_order_mgr.other_dir)
        if self.active_context:
            return self._ensure_directory(str(Path(self.active_context.backup_dir) / "other"))
        return ""

    def _resolve_dialog_initial_dir(
        self,
        default_dir: str,
        mode: str,
        custom_dir: str,
        last_dir: str,
    ) -> str:
        """
        解析文件选择器初始目录。
        回退链：
        1. 模式对应目录（custom / remember / default）
        2. 默认目录
        3. 上次记忆目录
        4. 空串（交给系统对话框决定）
        """
        normalized_default = self._normalize_existing_dir(default_dir)
        normalized_last = self._normalize_existing_dir(last_dir)
        normalized_custom = self._normalize_existing_dir(custom_dir)
        normalized_mode = str(mode or "default").strip().lower() or "default"

        if normalized_mode == "custom":
            return normalized_custom or normalized_default or normalized_last or ""
        if normalized_mode == "remember":
            return normalized_last or normalized_default or ""
        return normalized_default or normalized_last or ""

    def _remember_load_order_dialog_dir(self, kind: str, path_value: str | None):
        """
        仅在通过文件选择器且操作成功后调用，更新对应的全局“上次目录”。
        """
        normalized_dir = self._normalize_existing_dir(path_value)
        if not normalized_dir: return
        if kind == "import":
            settings.set("load_order_import_last_path", normalized_dir)
            return
        if kind == "export":
            settings.set("load_order_export_last_path", normalized_dir)

    def _on_app_loaded(self):
        """
        主窗口加载完毕回调。

        设计原则：
        1. `loaded` 说明 WebView 页面已经完成首轮加载，可以开始做“不会影响 splash 关闭”的后台预热；
        2. 这里不再承担“必须完成后才能显示窗口”的职责，避免把桌面模式首屏与社区库重建、监视器启动强绑定；
        3. 所有重活都改为后台线程执行，失败时只记录日志并给前端发送提示，不再阻塞首屏。
        """
        self._bind_native_drag_drop()
        self._start_startup_warmup()

    def _start_startup_warmup(self):
        """
        启动阶段后台预热。

        为什么挂在这里：
        - `API.__init__` 发生在主窗口创建前，适合做“没有就无法启动”的准备；
        - 社区工坊库 / 替代库缓存重建属于“有则更好”的能力，不应拖住桌面首屏；
        - 因此把它后移到窗口完成首轮加载后再后台执行，用户至少能先看到主界面。
        """
        if self._startup_warmup_started: return

        self._startup_warmup_started = True

        def background_warmup():
            startup_messages: list[str] = []
            try:
                if not self.workshop_db_mgr.cache_loaded:
                    logger.info("启动后台预热：开始加载社区工坊缓存与替代规则缓存")
                    self.workshop_db_mgr.load_all_cache()
                    if self.sorter and self.sorter.rule_mgr:
                        # 工坊缓存会影响依赖/替代规则判断，因此缓存热加载完成后要同步重建规则镜像。
                        self.sorter.rule_mgr.build_workshop_rules()
                    startup_messages.append("社区规则缓存已在后台完成预热。")
            except Exception as e:
                logger.error(f"启动后台预热失败: {e}", exc_info=True)
                startup_messages.append("社区缓存预热失败，首屏已继续打开；部分依赖/替代提示可能稍后才恢复。")
            finally:
                if startup_messages:
                    self._upgrade_context["messages"].extend(startup_messages)
                    EventBus.send_toast("\n".join(startup_messages), type="warning" if any("失败" in item for item in startup_messages) else "info")

        threading.Thread(
            target=background_warmup,
            name="rmm-startup-warmup",
            daemon=True,
        ).start()

    def _normalize_native_drop_selector(self, selector: str | None = None) -> str:
        """把前端传入的 id / selector 统一成 pywebview 可直接查询的 CSS 选择器。"""
        normalized = str(selector or self._native_drop_selector or '').strip() or '#backup-drop-zone'
        if normalized.startswith(('#', '.', '[')): return normalized
        return f'#{normalized}'

    def _bind_native_drag_drop(self, selector: str | None = None):
        """
        把原生 drop 事件只绑定到备份面板本体，减少整页级别监听带来的额外事件噪音。
        """
        if not self._window: return False

        normalized_selector = self._normalize_native_drop_selector(selector)

        try:
            from webview.dom import DOMEventHandler

            element = self._window.dom.get_element(normalized_selector)
            if not element:
                logger.debug(f"pywebview 原生 drop 区域暂未挂载: {normalized_selector}")
                return False

            if (
                self._native_drop_bound and
                normalized_selector == self._native_drop_selector and
                self._native_drop_element == element
            ): return True

            if self._native_drop_element and self._native_drop_handler:
                try:
                    self._native_drop_element.off('drop', self._native_drop_handler)
                except Exception:
                    # 旧节点已被 Vue 重建时，这里直接忽略即可。
                    pass

            callback = self._on_native_drop_event
            handler = DOMEventHandler(callback, True, True)
            element.on('drop', handler)
            self._native_drop_element = element
            self._native_drop_handler = callback
            self._native_drop_selector = normalized_selector
            self._native_drop_bound = True
            logger.info(f"已绑定 pywebview 原生 drop 事件: {normalized_selector}")
            return True
        except Exception as e:
            logger.warning(f"绑定 pywebview 原生 drop 事件失败: {e}")
            return False

    def _dispatch_native_drop_paths(self, full_paths: List[str]):
        """
        直接把文件路径送回前端的全局处理器，避免再经过事件总线序列化一层。
        """
        if not self._window or not full_paths: return

        try:
            payload = json.dumps(full_paths, ensure_ascii=False)
            self._window.evaluate_js(
                "window.setTimeout(function () {"
                f"  if (window.__rmm_handleNativeBackupDrop) window.__rmm_handleNativeBackupDrop({payload});"
                "}, 0);"
            )
        except Exception as e:
            logger.warning(f"回调前端原生拖放结果失败: {e}")

    def _on_native_drop_event(self, event):
        """
        只做一件事：取出 pywebview 注入的完整本地路径，并立即异步交回前端。
        """
        try:
            data_transfer = event.get('dataTransfer') or event.get('domTransfer') or {}
            files = data_transfer.get('files', [])
            full_paths = []
            for file_info in files:
                full_path = str(file_info.get('pywebviewFullPath') or '').strip()
                if full_path:
                    full_paths.append(full_path)
            if not full_paths: return
            threading.Thread(target=self._dispatch_native_drop_paths, args=(full_paths,), daemon=True).start()
        except Exception as e:
            logger.warning(f"处理原生拖放事件失败: {e}")

    @log_api_call
    def bind_backup_drop_zone(self, selector: str = 'backup-drop-zone'):
        """
        由前端在 BackupList 挂载后显式调用，确保 pywebview 绑定到真实存在的拖放区域。
        """
        normalized_selector = self._normalize_native_drop_selector(selector)
        if self.is_browser_runtime():
            return ApiResponse.success({"selector": normalized_selector, "native": False})
        if not self._window:
            return ApiResponse.error("主窗口尚未就绪")

        if self._bind_native_drag_drop(normalized_selector):
            return ApiResponse.success({"selector": normalized_selector})
        return ApiResponse.warning("拖放区域尚未挂载，稍后会重试", {"selector": normalized_selector})
    
    @log_api_call
    def monitor_force_wake(self):
        """强制唤醒主界面 (当游戏运行时)"""
        if self.game_monitor:
            self.game_monitor.force_wake()
        return ApiResponse.success()

    @log_api_call
    def monitor_force_sleep(self):
        """手动返回静默模式"""
        if self.game_monitor:
            self.game_monitor.force_sleep()
        return ApiResponse.success()

    @log_api_call
    def monitor_open_silent_logs(self):
        """静默模式下打开游戏日志页"""
        if self.game_monitor:
            self.game_monitor.open_idle_logs()
        return ApiResponse.success()

    @log_api_call
    def monitor_open_silent_home(self):
        """静默模式下返回主页"""
        if self.game_monitor:
            self.game_monitor.open_idle_home()
        return ApiResponse.success()
    
    @log_api_call
    def monitor_frontend_ready(self):
        """前端 Vue 挂载完毕后，主动调用此接口通知后端"""
        EventBus.resume()
        EventBus.mark_ready() # 激活 EventBus
        if self.game_monitor and not self.game_monitor.running:
            logger.info("前端已就绪，启动游戏监视器...")
            self.game_monitor.start()
        if self.game_monitor:
            # 告诉前端当前的游戏状态
            EventBus.emit('game-status-changed', {'running': self.game_monitor.is_game_running})
        logger.info("[EventBus] 收到前端就绪信号，事件总线已恢复")
        return ApiResponse.success()
    
    
    # =========================================================================
    #  1. 初始化与全局数据 (Initialization)
    # =========================================================================
    @log_api_call
    def get_initial_data(self):
        """
        前端启动时调用，一次性获取所有必要数据。
        """
        result = {
            "app_version": __version__,
            "build_mode": __build__,
            "runtime_mode": self._runtime_mode,
            "settings": asdict(settings.config), # 转为字典发给前端
            "asset_port": self.file_mgr.get_port(),
            "remote_image_cache": self.file_mgr.get_remote_cache_stats(),
            "context_healthy": False, 
            "health_report": {},
            "all_mods": [],  # 返回过滤后的列表
            "groups": [],
            "active_load_order": [],
            "active_load_modify_time": 0,
            "active_load_version_token": {},
            "is_first_db_init": self.is_first_db_init,
            "active_context": self.active_context if self.active_context else None,
            "upgrade_context": self._upgrade_context.copy() 
        }
        if not self.active_context or not self.active_context.is_healthy: return ApiResponse.success(result)
        
        # 2. 获取当前环境的 Mod 数据 (包含用户自定义数据), 并排除缺失的 Mod
        # 传入 None 让 DAO 自动读取 settings.current_profile_id
        # DAO 内部会自动处理：
        #   - 过滤掉非当前 Local 目录的 Mod
        #   - 过滤掉未启用 Workshop 环境下的 Workshop Mod
        #   - 执行 "Local 覆盖 Workshop" 的遮蔽策略
        context_mods = ModDAO.get_profile_mods(self.active_context)
        # 3. 获取所有分组数据 (结构化)
        # 传入当前的 assets 列表 ID，用于过滤掉分组中存在但当前环境下不可见的 Mod
        current_assets_ids = [m['package_id'] for m in context_mods]
        all_groups = GroupDAO.get_groups_structured_by_mod_ids(current_assets_ids)
        # 4. 获取当前激活的加载顺序
        active_load_order = self.load_order_mgr.read_active_mods() if self.load_order_mgr else {'active_mods': [], 'modify_time': 0}
        inactive_mods_order = self.active_context.inactive_mods_order if getattr(self.active_context, 'inactive_mods_order', []) else []
        
        replacements = self.workshop_db_mgr.get_replacements()
        replacements_map = {r['old_workshop_id']: r for r in replacements}
        
        dlc_parser = DLCParser(self.active_context.game_dlc_path)
        rule_mgr = self.sorter.rule_mgr if (self.sorter and self.sorter.rule_mgr) else None
        current_version = self.active_context.game_version[:3]
        
        # 新增：提取所有联锁组并做映射
        interlocks = list(ModInterlock.select().dicts())
        interlock_map = {i['id']: i['chain'] for i in interlocks}
        
        # 5. 数据加工：先注入翻译和生效规则，再统一计算语言包归属
        for mod in context_mods:
            # 翻译注入, 传入当前语言，Parser 内部会查找缓存
            if dlc_parser: dlc_parser.translate_record(mod, settings.config.language)
            # 注入清洗后的规则集
            if rule_mgr:
                mod['rules'] = rule_mgr.get_effective_mod_rules(mod['package_id'], mod)
            else:
                mod['rules'] = {}
        language_pack_owner_map = resolve_language_pack_ownership_for_mods(
            context_mods,
            user_mod_rules=(rule_mgr.user_mod_rules if rule_mgr else {}),
        )
        for mod in context_mods:
            mod['language_pack_owner_result'] = language_pack_owner_map.get(
                str(mod.get('package_id') or '').strip().lower(),
                {
                    "owners": [],
                    "analyzed_owners": [],
                    "relation_type": "unknown",
                    "summary_confidence": "unknown",
                    "analyzed_relation_type": "unknown",
                    "analyzed_summary_confidence": "unknown",
                }
            )
            if mod['workshop_id'] and  mod['workshop_id'] in replacements_map:
                mod['replacement'] = replacements_map[mod['workshop_id']]
            else:
                mod['replacement'] = None
        
        
        result.update({
            "all_mods": context_mods,  # 返回过滤后的列表
            "groups": all_groups,
            "interlocks": interlock_map,
            "active_load_order": active_load_order.get('active_mods', []),
            "inactive_load_order": inactive_mods_order,
            "active_load_modify_time": active_load_order.get('modify_time', 0),
            "active_load_version_token": active_load_order.get('version_token', {}),
        })
        
        self._reset_upgrade_context()
        if self.active_context.is_healthy and context_mods: 
            self.is_first_db_init = False   # 标记数据库已初始化
        
        return ApiResponse.success(result)
    
    def _reset_upgrade_context(self):
        """重置升级上下文，确保信息只在启动后下发一次"""
        self._upgrade_context = {
            "version_changed": False,
            "old_version": __version__,
            "new_version": __version__,
            "actions_taken": [],
            "pending_actions": [],
            "messages": []
        }

    def _start_tracked_main_db_task(self, task_name: str, target, *args) -> bool:
        """
        启动一个会触碰主库的后台线程，并在结束时主动关闭该线程的 SQLite 连接。
        """
        if self._db_maintenance_requested.is_set():
            logger.info("数据库维护中，跳过后台主库任务: %s", task_name)
            return False

        task_key = f"{task_name}:{uuid.uuid4().hex[:8]}"
        done_event = threading.Event()
        with self._db_background_task_lock:
            self._db_background_tasks[task_key] = done_event

        def runner():
            try:
                target(*args)
            finally:
                try:
                    if not db.is_closed():
                        db.close()
                except Exception:
                    logger.debug("后台主库任务关闭线程连接失败: %s", task_key, exc_info=True)
                done_event.set()
                with self._db_background_task_lock:
                    self._db_background_tasks.pop(task_key, None)

        threading.Thread(
            target=runner,
            daemon=True,
            name=f"DbTask-{task_name[:20]}",
        ).start()
        return True

    def _wait_for_tracked_main_db_tasks_idle(self, timeout: float = 10.0, poll_interval: float = 0.1) -> bool:
        """等待所有已登记的主库后台线程结束。"""
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            with self._db_background_task_lock:
                pending = list(self._db_background_tasks.keys())
            if not pending:
                return True
            time.sleep(min(poll_interval, max(0.01, deadline - time.time())))

        with self._db_background_task_lock:
            pending = list(self._db_background_tasks.keys())
        if pending:
            logger.warning("数据库维护前仍有后台主库任务未结束: %s", pending)
        return not pending

    def _finish_database_maintenance(self):
        """结束数据库维护窗口，允许后台数据库任务重新启动。"""
        self._db_maintenance_requested.clear()
    
    def _prepare_database_maintenance(self, timeout: float = 12.0):
        """
        在重置/修复数据库前，先停止会持有 SQLite 连接的后台任务。
        """
        deadline = time.time() + max(1.0, timeout)
        self._db_maintenance_requested.set()

        if self.scanner and self.scanner.is_scanning:
            logger.warning("数据库维护前检测到扫描任务仍在运行，准备中止并等待释放连接")
            self.scanner.stop_scan()

        if self.texture_mgr:
            active_analysis_tasks = self.texture_mgr.cancel_all_analysis_tasks()
            if active_analysis_tasks:
                logger.warning("数据库维护前取消贴图分析任务: %s", active_analysis_tasks)

        remaining = max(0.1, deadline - time.time())
        if self.scanner and not self.scanner.wait_until_idle(timeout=remaining):
            return False, "当前有扫描任务正在运行，请稍后再试。"

        remaining = max(0.1, deadline - time.time())
        if self.texture_mgr and not self.texture_mgr.wait_for_analysis_idle(timeout=remaining):
            return False, "当前有贴图任务正在运行，请稍后再试。"

        remaining = max(0.1, deadline - time.time())
        if not self._wait_for_tracked_main_db_tasks_idle(timeout=remaining):
            return False, "当前仍有后台数据库刷新任务在运行，请稍后再试。"

        return True, ""

    def _close_database_for_maintenance(self):
        """
        在数据库维护前主动关闭连接并释放文件句柄。
        原因：Windows 下 SQLite 文件切换、删除、重命名对句柄占用非常敏感。
        """
        try:
            close_db()
        except Exception:
            logger.warning("数据库维护前关闭连接失败", exc_info=True)
        gc.collect()
        time.sleep(0.5)

    def _restart_application(self, delay_seconds: float = 1.0):
        """
        延迟重启当前应用实例，确保 API 响应先返回给前端。
        """
        def worker():
            time.sleep(max(0.1, delay_seconds))
            try:
                self.cleanup()
            except Exception:
                logger.warning("重启前清理资源失败", exc_info=True)

            try:
                launch_new_application()
                logger.info("数据库修复完成，已拉起新实例，当前进程准备退出。")
            except Exception:
                logger.error("重启应用失败", exc_info=True)
                return

            os._exit(0)

        threading.Thread(target=worker, daemon=True, name="RestartAfterDbRepair").start()

    @log_api_call
    def reset_database(self):
        """
        重置数据库：强制关闭连接，删除文件，重建。
        """
        from backend.database.models import SystemInfo
        
        if not self._db_maintenance_lock.acquire(blocking=False):
            return ApiResponse.warning("当前正在处理数据库操作，请稍后再试。")
        try:
            ready, reason = self._prepare_database_maintenance()
            if not ready: return ApiResponse.warning(reason)
            self._close_database_for_maintenance()

            # 清理修复残留，避免重置后下次启动又应用旧的修复候选库。
            db_path = str(DATA_DIR / 'mod_manager.db')
            _cleanup_repair_artifacts(db_path, keep_failed_source=False)

            # 先尽量物理删除整库；删除失败时再回退到 clear_db，避免因为偶发占用直接整次失败。
            delete_error = None
            try:
                _remove_file_with_retry(db_path, retries=5, delay=0.4)
                _cleanup_database_sidecars(db_path)
            except Exception as e:
                delete_error = e
                logger.warning("主库物理删除失败，准备回退到逻辑清库: %s", e, exc_info=True)

            if os.path.exists(db_path):
                result = clear_db()
                if not result: return ApiResponse.error("重置失败，请关闭相关操作后重试。")
                self._close_database_for_maintenance()
            elif delete_error:
                logger.warning("主库已删除，但删除阶段存在告警: %s", delete_error)

            self.is_first_db_init = True
            init_ok = init_db(db_path)
            if not init_ok: return ApiResponse.error("重置失败，数据库无法重新创建。")
            # 重置后显式写回当前应用版本，避免少数 fallback 场景把旧元数据残留到下次启动。
            SystemInfo.insert(key='app_version', value=__version__).on_conflict_replace().execute()
            # 重置会清空所有环境记录，当前进程必须立即回退到 default 并重建上下文，
            # 否则内存里仍可能挂着已被删除的旧 profile manager / context。
            self._bootstrap_context('default')
            
            return ApiResponse.success({"message": "数据库已重置。"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ApiResponse.error(str(e))
        finally:
            self._finish_database_maintenance()
            self._db_maintenance_lock.release()

    @log_api_call
    def repair_database(self):
        """
        主动触发数据库修复：离线生成并校验候选库，成功后仅提示前端可重启切换。
        """
        if not self._db_maintenance_lock.acquire(blocking=False):
            return ApiResponse.warning("当前正在处理数据库操作，请稍后再试。")
        try:
            ready, reason = self._prepare_database_maintenance()
            if not ready: return ApiResponse.warning(reason)
            db_path = str(DATA_DIR / 'mod_manager.db')
            result = prepare_manual_database_repair(db_path)
            if not result: return ApiResponse.error("修复失败，请稍后重试。")
            if result.get("initialized"):
                self.is_first_db_init = True
                return ApiResponse.success({
                    "message": "未找到本地数据库，已为你重新创建。",
                    "restart_required": False,
                    "initialized": True,
                })
            if not result.get("restart_required"):
                return ApiResponse.error("修复失败，请稍后重试。")
            return ApiResponse.success({
                "message": "修复已完成，重启软件后生效。",
                "restart_required": True,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ApiResponse.error(str(e))
        finally:
            self._finish_database_maintenance()
            self._db_maintenance_lock.release()

    @log_api_call
    def restart_application(self):
        """
        主动重启应用。
        用途：手动修复准备完成后，由前端在用户确认后触发重启，不再在后端静默自动重启。
        """
        ready, reason = self._prepare_database_maintenance(timeout=15.0)
        if not ready:
            self._finish_database_maintenance()
            return ApiResponse.warning(reason)
        self._restart_application()
        return ApiResponse.success({"restarting": True}, message="软件即将重启。")
    
    @log_api_call
    def perform_database_cleanup(self):
        """手动触发：清理无效的 UserModData、GroupMod 和 ModAsset"""
        try:
            # 1. 清理文件已不存在的 ModAsset
            missing = ModMaintenanceDAO.find_missing_mods(delete=True)
            # 2. 清理孤立的用户数据和分组关联
            ModMaintenanceDAO.clean_orphaned_data()
            return ApiResponse.success(message="数据库清理完成")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    
    # =========================================================================
    #  2. 设置与路径 (Settings & Paths)
    # =========================================================================
    @log_api_call
    def auto_detect_paths(self, update_config: bool = True):
        """自动检测游戏路径"""
        result = self.game_mgr.auto_detect_paths()
        steam_path = self.steam_mgr.get_steam_path()
        if not result: return ApiResponse.error("无法自动检测到游戏路径，请手动设置！")
        result['steam_path'] = steam_path or ''
        if update_config:   # 仅当请求时更新配置
            settings.update_paths(result)
        # 如果检测到了安装路径，自动更新设置
        if result.get('game_install_path'):
            return ApiResponse.success({"paths": result})
        return ApiResponse.warning("仅检测到部分路径，请手动设置！",{"paths": result})

    @log_api_call
    def get_default_external_paths(self):
        """获取外部依赖页相关路径的默认值。"""
        default_paths = settings.get_default_external_paths()
        return ApiResponse.success({"paths": default_paths})

    @log_api_call
    def save_setting(self, key: str, value: Any):
        """保存单个设置项"""
        return self.save_all_settings({key: value})

    @log_api_call
    def save_all_settings(self, settings_obj: dict):
        """
        保存所有设置 (前端设置面板保存时调用)
        自动分流
        1. 识别环境字段 -> 更新 DB -> 重建 Context
        2. 识别全局字段 -> 更新 settings.config -> 保存 JSON
        """
        try:
            profile_data = {}
            global_data = {}
            # 这里的 PROFILE_KEYS 来自 ProfileManager 的定义
            profile_keys = self.profile_mgr.PROFILE_KEYS
            # 批量更新
            for k, v in settings_obj.items():
                # 如果修改的是核心路径，同步到当前环境
                if k in profile_keys:
                    profile_data[k] = v
                else:
                    # 只有 AppConfig 里定义的字段才进全局配置（过滤掉冗余的 UI 状态）
                    if hasattr(settings.config, k):
                        global_data[k] = v
            env_changed = False
            
            pid = self.active_context.profile_id if self.active_context else settings.config.current_profile_id
            
            # A. 处理环境数据
            if profile_data:
                profile_id = pid
                self.profile_mgr.update_profile(profile_id, profile_data)
                env_changed = True
            # B. 处理全局设置数据
            if global_data:
                settings.update_from_dict(global_data)  # recursive_update 批量更新
                network_mgr.apply() # 应用网络设置
                # 如果修改了某些会影响环境的全局路径（如 steamcmd_path）
                if 'steamcmd_path' in global_data or 'workshop_mods_path' in global_data:
                    env_changed = True
                rule_paths_changed = 'user_rules_path' in global_data or 'community_rules_path' in global_data
            else:
                rule_paths_changed = False
            if env_changed:
                logger.info("检测到核心路径变动，正在重新装配执行引擎...")
                # 重新调用 bootstrap，这会生成新的 ProfileContext 并重建所有 Manager
                self._bootstrap_context(pid)
            elif rule_paths_changed and self.sorter and self.sorter.rule_mgr:
                # 规则文件路径切换后必须立即重载，否则本次会话仍会持有旧文件内容。
                logger.info("检测到规则文件路径变动，正在重载规则缓存...")
                self.sorter.rule_mgr.load_all()
             
            return ApiResponse.success({
                "settings": asdict(settings.config),
                "active_context": self.active_context # 这里的 serialize_data 会自动调用 to_dict
                ,
                "remote_image_cache": self.file_mgr.get_remote_cache_stats(),
            }, message="配置保存成功")
            
        except Exception as e:
            logger.error(f"Save all settings failed: {str(e)}", exc_info=True)
            return ApiResponse.error(f"保存所有设置失败：{str(e)}")

    @log_api_call
    def get_remote_image_cache_stats(self):
        """获取网络图片缓存统计。"""
        return ApiResponse.success(self.file_mgr.get_remote_cache_stats())

    @log_api_call
    def clear_remote_image_cache(self):
        """清空网络图片缓存。"""
        cleared_stats = self.file_mgr.clear_remote_cache()
        return ApiResponse.success({
            "cleared": cleared_stats,
            "current": self.file_mgr.get_remote_cache_stats(),
        }, message="网络图片缓存已清空")

    @log_api_call
    def data_bundle_get_schema(self):
        """获取统一导入导出模块定义与环境清单。"""
        try:
            return ApiResponse.success(self.data_bundle_mgr.get_schema())
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def data_bundle_inspect(self, bundle_path: str):
        """读取数据包摘要，供前端在导入前展示确认信息。"""
        try:
            return ApiResponse.success(self.data_bundle_mgr.inspect_bundle(bundle_path))
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def data_bundle_export(self, payload: dict | None = None):
        """导出统一软件数据包。"""
        payload = payload or {}
        try:
            module_keys = list(payload.get("module_keys") or [])
            profile_ids = list(payload.get("profile_ids") or [])
            preset = str(payload.get("preset") or "custom").strip() or "custom"
            dynamic_rule_ids = payload.get("dynamic_rule_ids")
            suggested_name = str(payload.get("filename") or "").strip()
            if not suggested_name:
                if preset == "rules":
                    suggested_name = f"RimModManager_Rules_{datetime.now().strftime('%Y%m%d')}{DataBundleManager.FILE_EXTENSION}"
                else:
                    suggested_name = f"RimModManager_Data_{datetime.now().strftime('%Y%m%d')}{DataBundleManager.FILE_EXTENSION}"
            suggested_name = _ensure_bundle_filename_extension(
                suggested_name,
                DataBundleManager.FILE_EXTENSION,
                [DataBundleManager.FILE_EXTENSION, *DataBundleManager.LEGACY_FILE_EXTENSIONS],
            )

            target_path = file_mgr.save_file_dialog(
                initial_dir=str(DATA_DIR),
                default_filename=suggested_name,
                file_types=(
                    _build_dialog_file_type_label(
                        'RMM Data Package',
                        [DataBundleManager.FILE_EXTENSION, *DataBundleManager.LEGACY_FILE_EXTENSIONS],
                    ),
                    'All Files (*.*)',
                ),
            )
            if not target_path: return ApiResponse.warning("已取消")

            export_result = self.data_bundle_mgr.write_bundle(
                target_path=target_path,
                module_keys=module_keys,
                profile_ids=profile_ids,
                preset=preset,
                dynamic_rule_ids=dynamic_rule_ids,
            )
            return ApiResponse.success(export_result, message="导出成功")
        except Exception as e:
            logger.error(f"Data bundle export failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))

    @log_api_call
    def data_bundle_import(self, bundle_path: str, payload: dict | None = None):
        """导入统一软件数据包。"""
        payload = payload or {}
        try:
            module_keys = payload.get("module_keys")
            default_profile_mode = str(payload.get("default_profile_mode") or "clone").strip().lower() or "clone"
            profile_import_plan = payload.get("profile_import_plan")
            import_result = self.data_bundle_mgr.import_bundle(
                bundle_path,
                module_keys=module_keys,
                default_profile_mode=default_profile_mode,
                profile_import_plan=profile_import_plan,
            )

            network_mgr.apply()
            self._reload_current_profile_after_import(import_result)

            response_data = {
                "result": import_result,
                "settings": asdict(settings.config),
                "active_context": self.active_context,
            }
            message = "导入成功"
            if import_result.get("warnings"):
                message = f'导入完成，附带 {len(import_result["warnings"])} 条提示'
            return ApiResponse.success(response_data, message=message)
        except Exception as e:
            logger.error(f"Data bundle import failed: {e}", exc_info=True)
            return ApiResponse.error(f"导入失败: {e}")

    @log_api_call
    def mod_package_get_schema(self):
        """获取环境/模组打包所需的导入导出基础配置。"""
        try:
            return ApiResponse.success(self.mod_package_mgr.get_schema())
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def mod_package_prepare_import(self, bundle_path: str, payload: dict | None = None):
        """预检模组包导入冲突。"""
        try:
            return ApiResponse.success(self.mod_package_mgr.prepare_import(bundle_path, payload or {}))
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def mod_package_export(self, payload: dict | None = None):
        """导出模组实体包。"""
        payload = payload or {}
        try:
            suggested_name = str(payload.get("filename") or "").strip() or f"RimModManager_Mods_{datetime.now().strftime('%Y%m%d')}{self.mod_package_mgr.FILE_EXTENSION}"
            suggested_name = _ensure_bundle_filename_extension(
                suggested_name,
                self.mod_package_mgr.FILE_EXTENSION,
                [self.mod_package_mgr.FILE_EXTENSION, *self.mod_package_mgr.LEGACY_FILE_EXTENSIONS],
            )
            target_path = file_mgr.save_file_dialog(
                initial_dir=str(DATA_DIR),
                default_filename=suggested_name,
                file_types=(
                    _build_dialog_file_type_label(
                        'RMM Mod Package',
                        [self.mod_package_mgr.FILE_EXTENSION, *self.mod_package_mgr.LEGACY_FILE_EXTENSIONS],
                    ),
                    'All Files (*.*)',
                ),
            )
            if not target_path:
                return ApiResponse.warning("已取消")
            task_id = self.mod_package_mgr.start_export_task(target_path, payload)
            return ApiResponse.success({"task_id": task_id, "target_path": target_path}, message="导出任务已启动")
        except Exception as e:
            logger.error(f"Mod package export failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))

    @log_api_call
    def mod_package_get_profile_summary(self, profile_id: str):
        """读取指定环境的导出统计。"""
        try:
            return ApiResponse.success(self.mod_package_mgr.get_profile_export_summary(profile_id))
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def mod_package_import(self, bundle_path: str, payload: dict | None = None):
        """启动模组包导入任务。"""
        try:
            normalized_payload = dict(payload or {})
            normalized_payload["current_profile_id"] = str(settings.config.current_profile_id or "").strip()
            normalized_payload["current_local_mods_path"] = getattr(self.active_context, "local_mods_path", "") if self.active_context else ""
            task_id = self.mod_package_mgr.start_import_task(bundle_path, normalized_payload)
            return ApiResponse.success({"task_id": task_id}, message="导入任务已启动")
        except Exception as e:
            logger.error(f"Mod package import failed: {e}", exc_info=True)
            return ApiResponse.error(f"导入失败: {e}")
    
    @log_api_call
    def guide_mark_as_done(self, guide_key: str):
        """
        将指定的引导标记为已完成
        """
        try:
            # 使用 settings 管理器来安全地修改配置
            current_guides = settings.config.completed_guides
            current_guides[guide_key] = "done"
            settings.set('completed_guides', current_guides) # 这会自动触发保存
            return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def guide_reset_all(self):
        """
        重置所有引导状态
        """
        try:
            settings.set('completed_guides', {})
            return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(str(e))

    # =========================================================================
    #  3. Mod 扫描与管理 (Scanning & Mods)
    # =========================================================================
    @log_api_call
    def scan_mods(self, specific_paths: List[str]|None = None, forced_update: bool = False):
        """
        触发后台模组扫描。
        扫描完成后，Scanner 会回调当前环境的运行态收敛入口。
        立即返回状态，前端通过统一任务流和 `scan-complete` 事件获取更新。
        :param specific_paths: 可选，指定要扫描的路径列表。如果为空，则使用设置中的默认路径。
        :param forced_update: 可选，是否强制更新所有 Mod 的数据。默认 False。
        """
        try:
            paths_to_scan = []
            if specific_paths: paths_to_scan = specific_paths
            else:
                cfg = settings.config
                # 确保当前 Profile 已激活
                if not self.active_context:
                    self._bootstrap_context(settings.config.current_profile_id)
                
                if self.active_context:
                    # 1. DLC (Data 目录)
                    if os.path.exists(self.active_context.game_dlc_path):
                        paths_to_scan.append(self.active_context.game_dlc_path)
                    # 2. Local Mods (当前环境的 Mods 目录)
                    if os.path.exists(self.active_context.local_mods_path):
                        paths_to_scan.append(self.active_context.local_mods_path)
                    # 3. Self Mods (管理器的 Mods 目录)
                    if os.path.exists(cfg.self_mods_path):
                        paths_to_scan.append(cfg.self_mods_path)
                    # 4. Workshop Mods (公共工坊目录)
                    # 注意：库存扫描始终同步所有已配置域。
                    # use_workshop_mods / use_self_mods 只影响后续运行态冲突分析与链接部署，
                    # 不能影响数据库事实同步，否则工作区三库和缺失/更新状态会陈旧。
                    if os.path.exists(cfg.workshop_mods_path):
                        paths_to_scan.append(cfg.workshop_mods_path)
                    # 5. Tool Mods (工具模组目录)
                    if os.path.exists(str(TOOL_MODS_DIR)) and cfg.enable_tool_mods:
                        paths_to_scan.append(str(TOOL_MODS_DIR))
                else:
                    return ApiResponse.error("当前 环境 未激活，无法扫描 Mods")
            if not paths_to_scan: return ApiResponse.error("没有配置有效的扫描路径")
            # 调用异步扫描
            # 注意：这里不需要 try-catch 包裹整个逻辑，因为异常在线程内被捕获并通过事件发回了
            # 1. 扫描所有路径入库
            # 2. 识别 Local vs Workshop 冲突
            # 3. 触发当前环境的运行态收敛回调（若仍是当前环境）
            if not self.scanner: return ApiResponse.error("扫描器未初始化")
            result = self.scanner.scan_paths_async(paths_to_scan, forced_update=forced_update)
        except Exception as e:
            logger.error(f"Scan mods failed: {str(e)}", exc_info=True)
            return ApiResponse.error(f"扫描模组失败：{str(e)}")
        return ApiResponse.success({ "details": result },"后台扫描已启动")
    
    @log_api_call
    def scan_conflicts_resolve(self, operations: List[Dict], force: bool = False):
        """
        处理扫描发现的冲突。
        operations: List[Dict]
        [
            { 'action': 'disable', 'target_path': '...', 'keep_id': '...' },
            { 'action': 'delete', 'target_path': '...' }
        ]
        """
        results = []
        try:
            for op in operations:
                action = op.get('action')
                path = op.get('target_path')
                path_hash = str(op.get('target_path_hash') or '').strip()
                keep_hash = op.get('keep_path_hash')
                if not path:
                    continue

                success = False
                msg = ""
                try:
                    if action == 'disable':
                        # 1. 执行物理与数据库禁用
                        success, msg = ModMaintenanceDAO.set_mod_disabled_status(path, disable=True)
                        # 2. 如果提供了保留项的 Hash，记录阴影路径
                        if success and keep_hash:
                            ModMaintenanceDAO.add_shadow_path(keep_hash, path)
                    elif action == 'delete':
                        if not path_hash:
                            msg = "缺少 target_path_hash，无法删除该副本"
                        else:
                            op_force = bool(op.get('force_delete', force))
                            res = ModMaintenanceDAO.delete_mods_physically([path_hash], force=op_force)
                            success = res['success_count'] > 0
                            if not success:
                                msg = res['errors'][0] if res['errors'] else "未找到可删除的模组记录"
                    else:
                        msg = f"不支持的操作类型: {action}"
                except Exception as op_error:
                    msg = str(op_error)

                results.append({
                    'path': path,
                    'action': action,
                    'status': 'success' if success else 'error',
                    'msg': msg if not success else ''
                })

            success_count = sum(1 for item in results if item['status'] == 'success')
            error_items = [item for item in results if item['status'] != 'success']
            stats = {
                'total': len(results),
                'success_count': success_count,
                'error_count': len(error_items),
            }
            payload = {
                'results': results,
                'stats': stats,
                'failed_paths': [item['path'] for item in error_items]
            }

            if success_count == len(results):
                return ApiResponse.success(payload, "冲突处理完成")
            if success_count == 0:
                first_error = error_items[0]['msg'] if error_items else "没有可执行的操作"
                return ApiResponse.error(first_error, payload)
            return ApiResponse.warning(f"部分操作失败：{len(error_items)} 项未处理成功，其余操作已应用。", payload)
        except Exception as e:
            return ApiResponse.error(f"处理出错: {str(e)}")
    
    @log_api_call
    def mods_delete(self, path_hashes: List[str]|str, force: bool = False):
        """
        批量物理删除 Mod 并抹除数据库记录
        :param paths: 绝对路径列表
        """
        try:
            normalized_hashes = self._normalize_str_items(path_hashes)
            res = ModMaintenanceDAO.delete_mods_physically(normalized_hashes, force=force)
            res['force'] = bool(force)
            return self._build_delete_response("Mod", len(normalized_hashes), res)
        except Exception as e:
            return ApiResponse.error(f"删除失败: {str(e)}")
    
    @log_api_call
    def mods_disable(self, path_hashes: List[str], disabled: bool = True):
        """
        禁用或启用指定 Mod。
        :param package_id: Mod 的 package_id
        :param disabled: 是否禁用 (True) 或启用 (False)
        """
        try:
            for path_hash in path_hashes:
                # 1. 校验 path_hash 是否存在
                mod = ModAsset.get_or_none(ModAsset.path_hash == path_hash)
                if not mod: continue
                # 2. 执行禁用/启用操作
                ModMaintenanceDAO.set_mod_disabled_status(mod.path, disabled)
            return ApiResponse.success(message=f"Mod {'已禁用' if disabled else '已启用'}")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mod_time_update(self, mods_data_list: List[Dict[str, Any]]):
        """
        更新指定 Mod 列表 的 最后操作时间
        """
        try:
            # 净化数据只保留必要字段
            valid_fields = ['path_hash', 'last_active_time', 'last_moved_time']
            mods_data_list = [{k: v for k, v in mod.items() if k in valid_fields} for mod in mods_data_list]
            # print(f"更新Mod最后操作时间:{mods_data_list}")
            ModDAO.batch_update_mods(mods_data_list)
            return ApiResponse.success(message='最后操作时间已更新')
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mod_user_data_update(self, package_id: str, data_dict: dict):
        """
        即时保存用户对 Mod 的修改 (标签, 备注, 颜色等)
        """
        try:
            ModDAO.update_user_data(package_id, data_dict)
            return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mods_user_data_update(self, user_data_list: List[Dict[str, Any]]):
        """
        通用批量更新用户自定义数据 (别名、备注、标签等)
        user_data_list 结构示例: [{'mod_id': 'xxx', 'alias_name': 'yyy', 'notes': 'zzz'}]
        """
        try:
            # 过滤掉没有 mod_id 的非法数据
            valid_list = [d for d in user_data_list if 'mod_id' in d]
            if valid_list:
                ModDAO.batch_upsert_user_data(valid_list)
            return ApiResponse.success(message=f'已成功应用 {len(valid_list)} 项数据')
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mods_ignore_issues_update(self, mods_data_list: List[Dict[str, Any]]):
        """
        批量更新用户对 Mod 的修改
        """
        try:
            # 净化数据只保留必要字段
            valid_fields = ['mod_id', 'ignored_issues']
            mods_data_list = [{k: v for k, v in mod.items() if k in valid_fields} for mod in mods_data_list]
            ModDAO.batch_upsert_user_data(mods_data_list)
            return ApiResponse.success(message='用户数据已更新')
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mods_sign_color_update(self, mod_ids: List[str], color: str):
        """批量设置 Mod 颜色"""
        try:
            ModDAO.set_mods_color(mod_ids, color)
            return ApiResponse.success(message="颜色已设置")
        except Exception as e:
            return ApiResponse.error((mod_ids, color, str(e)))
    
    @log_api_call
    def mods_user_mod_type_update(self, mod_ids: List[str], new_type: str):
        """批量设置用户自定义 Mod 类型"""
        try:
            ModDAO.set_user_mods_type(mod_ids, new_type)
            return ApiResponse.success(message="类型已设置")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def mods_link(self, mod_ids: List[str]):
        """批量设置 Mod 联锁"""
        try:
            result = ModInterlockDAO.link_mods(mod_ids)
            return ApiResponse.success(data=result)
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def mods_unlink(self, mod_ids: List[str]):
        """批量解除 Mod 联锁"""
        try:
            result = ModInterlockDAO.unlink_mods(mod_ids)
            return ApiResponse.success(data=result)
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mods_interlock_heal(self, interlock_id: str):
        """修复断裂的联锁组（剔除本地缺失项）"""
        try:
            result = ModInterlockDAO.heal_interlock(interlock_id)
            return ApiResponse.success(data=result, message="联锁修复完成")
        except Exception as e:
            return ApiResponse.error(str(e))
            
    @log_api_call
    def mods_interlock_missing_get(self, interlock_id: str):
        """获取联锁组中缺失的项，供前端引导订阅"""
        try:
            missing_mods = ModInterlockDAO.get_interlock_missing_mods(interlock_id)
            return ApiResponse.success(data=missing_mods)
        except Exception as e:
            return ApiResponse.error(str(e))
    
    
    @log_api_call
    def mods_add_tags(self, mod_ids: List[str], tags: List[str]):
        """批量添加标签"""
        try:
            ModDAO.add_tags_to_mods(mod_ids, tags)
            return ApiResponse.success(message="标签已添加")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def mods_remove_tags(self, mod_ids: List[str], tags: List[str]):
        """批量移除标签"""
        try:
            ModDAO.remove_tags_from_mods(mod_ids, tags)
            return ApiResponse.success(message="标签已移除")
        except Exception as e:
            return ApiResponse.error(str(e))
        
    
    # =========================================================================
    #  4. 分组管理 (Groups) - 即时保存
    # =========================================================================

    @log_api_call
    def groups_get(self):
        context_mods = ModDAO.get_profile_mods(self.active_context) 
        # 传入当前的 assets 列表 ID，用于过滤掉分组中存在但当前环境下不可见的 Mod
        current_assets_ids = [m['package_id'] for m in context_mods]
        return ApiResponse.success(GroupDAO.get_groups_structured_by_mod_ids(current_assets_ids))

    @log_api_call
    def group_create(self, name: str, color: str):
        try:
            # 后端生成 UUID 并入库
            new_group = GroupDAO.create_group(name, color)
            data = {
                "group": {
                    "group_id": new_group.group_id,
                    "name": new_group.name,
                    "color": new_group.color,
                    "sort_index": new_group.sort_index,
                    "is_expanded": new_group.is_expanded,
                    "mod_ids": []
                }
            }
            # 返回完整对象供前端渲染
            return ApiResponse.success(data)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def group_delete(self, group_id: str):
        return ApiResponse.success(GroupDAO.delete_group(group_id))

    @log_api_call
    def group_update(self, group_id: str, updates: dict):
        """更新分组属性 (重命名、改色、折叠)"""
        # print(f"更新分组 {group_id} 为 {updates}")
        return ApiResponse.success(GroupDAO.update_group_info(group_id, **updates))

    @log_api_call
    def group_add_mods(self, group_id: str, mod_ids: List[str]):
        """拖拽 Mod 进分组"""
        return ApiResponse.success(GroupDAO.add_mods_to_group(group_id, mod_ids))

    @log_api_call
    def group_remove_mods(self, group_id: str, mod_ids: List[str]):
        """从分组移除 Mod"""
        return ApiResponse.success(GroupDAO.remove_mods_from_group(group_id, mod_ids))
    
    @log_api_call
    def groups_expansion_all(self, is_expanded: bool):
        """一次性展开或折叠所有分组"""
        GroupDAO.update_all_expansion_state(is_expanded)
        return ApiResponse.success()
    
    @log_api_call
    def group_reorder(self, group_id_list: List[str]):
        """分组排序"""
        return ApiResponse.success(GroupDAO.reorder_groups(group_id_list))
    
    @log_api_call
    def group_content_reorder(self, group_id: str, mod_id_list: List[str]):
        """分组内 Mod 排序"""
        return ApiResponse.success(GroupDAO.reorder_mods_in_group(group_id, mod_id_list))


    # =========================================================================
    #  5. 加载顺序与游戏启动 (Load Order & Launch)
    # =========================================================================
    
    @log_api_call
    def load_order_get(self):
        """
        获取当前的加载顺序
        :param mods_config_file_path: 排序文件路径
        :return: [package_id, package_id, ...]
        """
        try:
            if not self.load_order_mgr: 
                return ApiResponse.error("加载顺序管理器未初始化")
            res = self.load_order_mgr.read_active_mods()
            if not res or not res.get('active_mods', []):
                return ApiResponse.error("已启用的Mod为空，或文件读取失败!")
        except Exception as e:
            return ApiResponse.error(f"读取加载顺序文件出错: {e}")
        return ApiResponse.success({
            "file": self.active_context.mods_config_file if self.active_context else "",
            "active_ids": res.get('active_mods', []),
            "modify_time": res.get('modify_time', 0),
            # 统一把格式和结构化模组明细一起返回，方便前端直接显示名称并处理订阅。
            "format": res.get('format', 'modsconfig'),
            "list_name": res.get('list_name', ''),
            "mods": res.get('mods', []),
            "mod_names": res.get('mod_names', []),
            "mod_steam_workshop_ids": res.get('mod_steam_workshop_ids', []),
            "workshop_ids": res.get('workshop_ids', []),
            "warnings": res.get('warnings', []),
            "errors": res.get('errors', []),
            "import_check": res.get('import_check', {"summary": {}, "items": []}),
            "version_token": res.get('version_token', {}),
        })

    @log_api_call
    def mod_config_get_overview(self):
        """读取当前环境下官方 ModSettings 配置文件总览。"""
        if not self.active_context:
            return ApiResponse.error("当前环境未初始化")
        active_tokens = []
        if self.load_order_mgr:
            active_tokens = list((self.load_order_mgr.read_active_mods() or {}).get("active_mods", []) or [])
        try:
            overview = ModConfigManager.get_overview(self.active_context, active_tokens)
            return ApiResponse.success(overview)
        except Exception as e:
            return ApiResponse.error(f"读取模组配置总览失败: {e}")

    @log_api_call
    def mod_config_sync(self, source_path: str, target_path: str):
        """在同一 package_id 分组内手动覆盖同步配置文件。"""
        if not self.active_context:
            return ApiResponse.error("当前环境未初始化")
        active_tokens = []
        if self.load_order_mgr:
            active_tokens = list((self.load_order_mgr.read_active_mods() or {}).get("active_mods", []) or [])
        try:
            result = ModConfigManager.sync_group_instance(
                self.active_context,
                active_tokens,
                source_path,
                target_path,
            )
            return ApiResponse.success(result, message="已完成配置覆盖")
        except Exception as e:
            return ApiResponse.error(f"覆盖配置失败: {e}")

    @log_api_call
    def load_order_file_open(self, mods_config_file_path: str|None = None, profile_id: str | None = None):
        """
        打开任意支持的排序文件
        """
        from backend.managers.mgr_load_order import LOAD_ORDER_OPEN_FILE_TYPES
        context, profile = self._resolve_load_order_scope(profile_id)
        source_profile_id = str(profile_id or "").strip()
        file = ''
        from_dialog = False
        # 默认路径为 ModsConfig.xml 所在目录
        if not mods_config_file_path:
            mods_config_file_path = self._resolve_dialog_initial_dir(
                self._get_default_import_dir(context),
                settings.config.load_order_import_dir_mode,
                settings.config.load_order_import_custom_path,
                settings.config.load_order_import_last_path,
            )
        # 解析逻辑已经支持 xml / json / txt / rws 等多种格式。
        # 这里不再按扩展名硬编码拦截，只要是实际存在的文件就允许继续解析。
        if os.path.isfile(mods_config_file_path):
            file = mods_config_file_path
        elif os.path.isdir(mods_config_file_path) :
            from_dialog = True
            file = file_mgr.select_file_dialog(
                initial_dir=mods_config_file_path,
                file_types=LOAD_ORDER_OPEN_FILE_TYPES,
            )
        else:
            from_dialog = True
            file = file_mgr.select_file_dialog(
                initial_dir=self._resolve_dialog_initial_dir(
                    self._get_default_import_dir(context),
                    settings.config.load_order_import_dir_mode,
                    settings.config.load_order_import_custom_path,
                    settings.config.load_order_import_last_path,
                ),
                file_types=LOAD_ORDER_OPEN_FILE_TYPES,
            )
        if not file: return ApiResponse.warning("未选择文件")
        res = self.load_order_mgr.read_active_mods(file) if self.load_order_mgr else {}
        result = self._build_load_order_result(
            file,
            res,
            source_profile_id=source_profile_id,
            source_profile_name=profile.name if profile else "",
        )
        # 对于 workshop id 列表这类文件，可能没有 package_id，但仍然是有效输入。
        if not result["active_ids"] and not result["workshop_ids"]:
            return ApiResponse.error("解析文件出错!")
        if from_dialog:
            self._remember_load_order_dialog_dir("import", file)
        return ApiResponse.success(result)

    @log_api_call
    def load_order_file_import_payload(self, payload: Any, profile_id: str | None = None):
        """
        浏览器模式下导入拖放的文件内容。
        标准浏览器不会暴露本地绝对路径，因此这里先落临时文件，再复用现有解析流程。
        """
        normalized_name, raw_bytes = self._decode_browser_import_payload(payload)
        source_profile_id = str(profile_id or "").strip()
        _context, profile = self._resolve_load_order_scope(profile_id)
        temp_path = self._write_browser_import_temp_file(normalized_name, raw_bytes)
        res = self.load_order_mgr.read_active_mods(temp_path) if self.load_order_mgr else {}
        result = self._build_load_order_result(
            temp_path,
            res,
            source_profile_id=source_profile_id,
            source_profile_name=profile.name if profile else "",
            list_name_override=Path(normalized_name).stem,
        )
        if not result["active_ids"] and not result["workshop_ids"]:
            return ApiResponse.error("解析文件出错!")
        return ApiResponse.success(result)
    
    @log_api_call
    def load_order_inactive_save(self, inactive_ids: List[str]):
        """
        保存用户自定义的停用列表顺序 (包含清空后的 Temp 列表)
        """
        if not self.active_context: return ApiResponse.error("环境配置上下文缺失")
        try:
            result = self.profile_mgr.update_profile( self.active_context.profile_id, {"inactive_mods_order": inactive_ids})
            if result: return ApiResponse.success()
            return ApiResponse.error("更新配置失败")
        except Exception as e:
            return ApiResponse.error(f"保存停用列表顺序时出错: {e}")
    
    @log_api_call
    def load_order_save(self, active_ids: List[str], is_dirty: bool=True):
        """
        保存当前激活列表到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        """
        return self.load_order_save_with_token(active_ids, is_dirty=is_dirty, base_version_token=None)

    @log_api_call
    def load_order_save_with_token(self, active_ids: List[str], is_dirty: bool=True, base_version_token: dict | None = None):
        """
        保存当前激活列表到 ModsConfig.xml，并阻止对过期磁盘版本的静默覆盖。
        """
        if not self.active_context: return ApiResponse.error("环境配置上下文缺失")
        if not self.active_context.game_config_path or not os.path.exists(self.active_context.game_config_path):
            return ApiResponse.error("未指定游戏配置路径")
        try:
            if self.load_order_mgr:
                is_stale, current_token = self.load_order_mgr.is_version_token_stale(base_version_token)
                if is_stale:
                    disk_result = self.load_order_mgr.read_active_mods()
                    return ApiResponse.warning(
                        "磁盘加载顺序已被外部修改，请先处理冲突。",
                        self._build_save_conflict_payload(disk_result, active_ids),
                    )
            success = self.load_order_mgr.save_active_mods(active_ids, is_dirty=is_dirty) if self.load_order_mgr else False
            if success:
                latest = self.load_order_mgr.read_active_mods() if self.load_order_mgr else {}
                return ApiResponse.success({
                    "saved": True,
                    "version_token": latest.get("version_token", current_token if self.load_order_mgr else {}),
                    "modify_time": latest.get("modify_time", 0),
                    "active_ids": latest.get("active_mods", []),
                })
            return ApiResponse.warning("取消保存")
        except Exception as e:
            return ApiResponse.error(f"保存 ModsConfig.xml 时出错: {e}")
    
    @log_api_call
    def load_order_export(self, active_ids: List[str], target_path: str|None = None, trigger_dialog: bool = True, export_format: str = 'modsconfig', list_name: str | None = None, remember_dialog_dir: bool = False):
        """
        导出当前加载顺序到指定格式
        :param active_ids: 激活的 Mod 列表
        :param target_path: 导出路径
        """
        try:
            if not target_path and not trigger_dialog: trigger_dialog = True
            # 导出格式和列表名都透传给 LoadOrderManager，
            # 由底层统一决定生成 ModsConfig.xml 还是 ModList.xml。
            success = self.load_order_mgr.save_active_mods(
                active_ids,
                target_path,
                trigger_dialog,
                export_format=export_format,
                list_name=list_name
            ) if self.load_order_mgr else False
            if success:
                if remember_dialog_dir:
                    self._remember_load_order_dialog_dir("export", target_path)
                return ApiResponse.success()
            return ApiResponse.warning("取消保存")
        except Exception as e:
            return ApiResponse.error(f"导出加载顺序时出错: {e}")

    @log_api_call
    def load_order_export_pick_path(self, export_format: str = 'modsconfig'):
        if not self.load_order_mgr:
            return ApiResponse.error("加载顺序管理器未初始化")
        try:
            export_format = str(export_format or 'modsconfig').strip().lower() or 'modsconfig'
            default_name = self.load_order_mgr._default_export_name(export_format)
            file_types = self.load_order_mgr._get_save_file_types(export_format)
            initial_dir = self._resolve_dialog_initial_dir(
                self._get_default_export_dir(),
                settings.config.load_order_export_dir_mode,
                settings.config.load_order_export_custom_path,
                settings.config.load_order_export_last_path,
            )
            selected = FileManager.save_file_dialog(
                initial_dir=initial_dir,
                default_filename=default_name,
                file_types=file_types,
            )
            if not selected:
                return ApiResponse.warning("未选择导出路径")
            return ApiResponse.success({"path": selected})
        except Exception as e:
            return ApiResponse.error(f"选择导出路径时出错: {e}")

    @log_api_call
    def load_order_share_export(self, active_ids: List[str], list_name: str | None = None):
        """
        把当前加载顺序导出为分享码。
        """
        if not self.load_order_mgr:
            return ApiResponse.error("加载顺序管理器未初始化")
        try:
            share_code = self.load_order_mgr.export_share_code(
                active_ids,
                list_name=list_name,
            )
            return ApiResponse.success({
                "share_code": share_code,
                "format": "share_code",
                "count": len(active_ids or []),
            })
        except Exception as e:
            return ApiResponse.error(f"生成分享码时出错: {e}")

    @log_api_call
    def load_order_share_import(self, share_code: str, profile_id: str | None = None):
        """
        解析分享码并返回与文件导入相同的数据结构。
        """
        try:
            if not self.load_order_mgr:
                return ApiResponse.error("加载顺序管理器未初始化")
            res = self.load_order_mgr.read_share_code(share_code)
            return ApiResponse.success({
                "file": res.get("share_code_ref", "share://RMM1"),
                "active_ids": res.get('active_mods', []),
                "modify_time": res.get('modify_time', 0),
                "format": res.get('format', 'share_code'),
                "list_name": res.get('list_name', ''),
                "mods": res.get('mods', []),
                "mod_names": res.get('mod_names', []),
                "mod_steam_workshop_ids": res.get('mod_steam_workshop_ids', []),
                "workshop_ids": res.get('workshop_ids', []),
                "warnings": res.get('warnings', []),
                "errors": res.get('errors', []),
                "import_check": res.get('import_check', {"summary": {}, "items": []}),
                "share_code": res.get("share_code", ""),
                "share_code_ref": res.get("share_code_ref", ""),
                "source_profile_id": str(profile_id or "").strip(),
            })
        except Exception as e:
            return ApiResponse.error(f"解析分享码时出错: {e}")

    @log_api_call
    def backups_get_all(self, profile_id: str | None = None):
        """获取所有备份文件路径"""
        try:
            context, profile = self._resolve_load_order_scope(profile_id)
            load_order_mgr = LoadOrderManager(context)
            backups = load_order_mgr.get_all_backups() if load_order_mgr else {"today": [], "earlier": [], "other": []}
            return ApiResponse.success({
                **backups,
                "profile": {
                    "id": context.profile_id,
                    "name": profile.name,
                    "backup_dir": context.backup_dir,
                    "is_current": bool(self.active_context and context.profile_id == self.active_context.profile_id),
                    "is_healthy": context.is_healthy,
                }
            })
        except Exception as e:
            return ApiResponse.error(f"获取备份文件时出错: {e}")
    
    @log_api_call
    def game_launch(self, profile_id: str):
        """启动游戏"""
        try:
            if not profile_id: profile_id = self.profile_mgr.current_profile.id
            if not profile_id: return ApiResponse.error("未指定 Profile ID")
            profile = self.profile_mgr.get_profile(profile_id)
            extra_args = self.profile_mgr.get_launch_args(profile_id, include_executable=False)
            runtime_caps = self._resolve_profile_runtime_caps_from_profile(profile)
            prefer_steam_launch = bool(runtime_caps.get('steam_launch_enabled'))
            is_steam_managed = bool(runtime_caps.get('is_steam_managed'))
            # 检查 Steam 路径是否有效，无效则尝试重新获取
            if prefer_steam_launch and not settings.config.steam_path:
                settings.config.steam_path = self.steam_mgr.get_steam_path() or ''
            steam_path_valid = bool(
                settings.config.steam_path
                and PathChecker.check_steam_path(settings.config.steam_path).get('pass', False)
            )
            steam_status = self.steam_mgr.get_steam_client_status()
            steam_running = bool(steam_status.get("running"))
            steam_ready = bool(steam_status.get("ready"))
            logger.debug(
                "launch_game: profile_id=%s, prefer_steam=%s, steam_path_valid=%s, steam_running=%s, steam_ready=%s, steam_source=%s, steam_detail=%s, is_steam=%s, is_steam_managed=%s",
                profile_id,
                prefer_steam_launch,
                steam_path_valid,
                steam_running,
                steam_ready,
                steam_status.get("source"),
                steam_status.get("detail"),
                profile.is_steam,
                is_steam_managed,
            )

            if prefer_steam_launch:
                if is_steam_managed:
                    # Steam 管理主版本可以走 Steam 官方入口。
                    # 进入 Steam 前先清掉额外 Workshop 链接，避免“Steam 自动挂载 + 本地链接部署”重复参与。
                    self._ensure_runtime_links_for_launch(profile_id, include_workshop=False)

                    if steam_path_valid:
                        game_monitor = getattr(self, "game_monitor", None)
                        if game_monitor:
                            game_monitor.launch_profile_id = profile_id
                        self.steam_mgr.launch_via_steam_cmd(extra_args=extra_args)
                        return ApiResponse.success(message="通过 Steam 启动游戏成功，祝你游玩愉快！")

                    if profile.id == 'default':
                        try:
                            game_monitor = getattr(self, "game_monitor", None)
                            if game_monitor:
                                game_monitor.launch_profile_id = profile_id
                            os.startfile(f"steam://run/{RIMWORLD_APP_ID}")
                            return ApiResponse.warning(
                                message="未检测到有效的 Steam 程序路径，已尝试通过 URL 协议启动 Steam 游戏；如果失败，请检查 Steam 客户端状态或关闭“优先 Steam 启动”选项。"
                            )
                        except Exception as e:
                            logger.warning(f"Launch Steam game via URL failed: {e}", exc_info=True)

                    return self._build_direct_launch_confirmation(
                        profile_id=profile_id,
                        steam_running=bool(steam_running),
                        reason="steam_path_invalid",
                        message="当前环境配置为优先使用 Steam 启动，但未检测到有效的 Steam 程序路径，无法安全自动启动。您可以继续改为游戏本体直启，或先修复 Steam 路径后重试。",
                        requires_fallback_confirm=True,
                        steam_status=self._attach_steam_user_hint(steam_status),
                    )
                # 非 Steam 管理主版本的 Steam 正版副本：
                # 不适合再假装它是“官方 AppID 安装”，但仍然可以通过
                # “先等 Steam 就绪，再直启游戏本体”的方式进入 Steam 运行态。
                ok, ensured_status, message = self._ensure_steam_ready(timeout_seconds=45)
                if ok:
                    self._launch_profile_with_runtime_links(profile_id, profile.game_install_path, extra_args, include_workshop=False)
                    return ApiResponse.success(message="通过 Steam 启动游戏成功，祝你游玩愉快！")

                # Steam 客户端未进入可用状态，提示用户确认
                return self._build_direct_launch_confirmation(
                    profile_id=profile_id,
                    steam_running=bool((ensured_status or {}).get("running")),
                    reason=str((ensured_status or {}).get("reason") or "steam_not_ready"),
                    message=message or "Steam 未能进入可用状态。您可以继续改为游戏本体直启，或稍后重试。",
                    requires_fallback_confirm=True,
                    steam_status=ensured_status,
                )

            # 不使用Steam启动，且Steam 已在运行，提示用户确认
            if steam_running and bool(runtime_caps.get('is_steam')):
                return self._build_direct_launch_confirmation(
                    profile_id=profile_id,
                    steam_running=True,
                    reason="steam_running_conflict",
                    message="检测到 Steam 已在运行，当前环境若继续以游戏本体直启，Steam 可能会接管本次启动并同时加载工坊内容。",
                    steam_status=steam_status,
                )

            # 不使用Steam启动，且Steam 未在运行，直接启动游戏本体
            self._launch_profile_with_runtime_links( profile_id, profile.game_install_path, extra_args, include_workshop=True )

            # 使用Steam启动，且Steam路径无效，提示用户
            if prefer_steam_launch and not steam_path_valid:
                return ApiResponse.warning(message="未检测到有效的 Steam 程序路径，已自动切换为游戏本体直接启动。")
            return ApiResponse.success(message="直接启动游戏成功，祝你游玩愉快！")
        except Exception as e:
            logger.error(f"Launch Game Error: {e}", exc_info=True)
            return ApiResponse.error(f"启动游戏时出错: {e}")

    @staticmethod
    def _build_runtime_link_sync_fingerprint(
        profile_id: str,
        local_mods_root: str,
        include_workshop: bool,
        runtime_caps: dict[str, Any],
        deploy_paths: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        normalized_root = os.path.normpath(str(local_mods_root or "")).lower()
        normalized_deploy_paths = tuple(
            sorted(
                os.path.normpath(str(path)).lower()
                for path in (deploy_paths or [])
                if str(path or "").strip()
            )
        )
        return {
            "profile_id": str(profile_id or "").strip(),
            "local_mods_root": normalized_root,
            "include_workshop": bool(include_workshop),
            "workshop_detection_enabled": bool(runtime_caps.get('workshop_detection_enabled')),
            "workshop_deploy_enabled": bool(include_workshop and runtime_caps.get('workshop_deploy_enabled')),
            "deploy_paths": normalized_deploy_paths,
        }

    def _sync_runtime_links_for_profile(self, profile_id: str, include_workshop: bool):
        """
        按指定环境的运行方式收敛本地 Mods 链接。
        include_workshop=False 时，相当于仅移除 Workshop 链接，同时保留 Self/Tool 的有效链接。
        """
        context = self.profile_mgr.build_profile_context(profile_id)
        local_mods_root = context.local_mods_path
        runtime_link_sync_state = getattr(self, "_runtime_link_sync_state", {})
        normalized_profile_id = str(profile_id or "").strip()
        if not local_mods_root or not os.path.exists(local_mods_root):
            runtime_link_sync_state.pop(normalized_profile_id, None)
            self._runtime_link_sync_state = runtime_link_sync_state
            self._last_runtime_link_sync_result = {"profile_id": normalized_profile_id, "status": "missing_root"}
            return False
        runtime_caps = resolve_profile_runtime_capabilities(context)
        runtime_analysis = ModDAO.get_profile_conflict_analysis(
            context,
            include_workshop_in_detection=bool(runtime_caps.get('workshop_detection_enabled')),
            include_workshop_in_deploy=bool(include_workshop and runtime_caps.get('workshop_deploy_enabled')),
        )
        deploy_paths = runtime_analysis.get('deploy_paths', [])
        sync_fingerprint = self._build_runtime_link_sync_fingerprint(
            normalized_profile_id,
            local_mods_root,
            include_workshop,
            runtime_caps,
            deploy_paths,
        )
        if runtime_link_sync_state.get(normalized_profile_id) == sync_fingerprint:
            logger.debug("Runtime links already up to date for profile %s", normalized_profile_id)
            self._last_runtime_link_sync_result = {"profile_id": normalized_profile_id, "status": "noop"}
            return True

        success = self.file_mgr.sync_managed_links(local_mods_root, deploy_paths)
        if success:
            runtime_link_sync_state[normalized_profile_id] = sync_fingerprint
            self._runtime_link_sync_state = runtime_link_sync_state
            self._last_runtime_link_sync_result = {"profile_id": normalized_profile_id, "status": "deployed"}
        else:
            self._last_runtime_link_sync_result = {"profile_id": normalized_profile_id, "status": "failed"}
        return success

    def _sync_runtime_links_after_scan(self, scanned_profile_id: str) -> str:
        """
        扫描写库后的统一部署入口。
        只允许当前激活环境执行，避免旧扫描任务把新环境链接回滚。
        """
        active_profile_id = str(getattr(getattr(self, 'active_context', None), 'profile_id', '') or '').strip()
        target_profile_id = str(scanned_profile_id or '').strip()
        if not active_profile_id or active_profile_id != target_profile_id:
            return "Skipped runtime link sync for stale profile"

        success = self._sync_runtime_links_for_profile(target_profile_id, include_workshop=True)
        sync_status = str(getattr(self, "_last_runtime_link_sync_result", {}).get("status", "") or "").strip()
        if success and sync_status == "deployed":
            return "Deployed runtime links"
        return "Runtime links already up to date" if success and sync_status == "noop" else "Runtime link sync skipped"

    def _ensure_runtime_links_for_launch(self, profile_id: str, include_workshop: bool) -> bool:
        """
        启动前兜底检查。
        如果当前进程里已经对同一激活环境收敛到相同运行模式，则直接跳过；
        只有缺少收敛记录、目标环境不是当前激活环境，或启动模式发生变化时才真正执行收敛。
        """
        normalized_profile_id = str(profile_id or "").strip()
        active_profile_id = str(getattr(getattr(self, 'active_context', None), 'profile_id', '') or '').strip()
        current_state = getattr(self, "_runtime_link_sync_state", {}).get(normalized_profile_id)
        if (
            current_state
            and active_profile_id == normalized_profile_id
            and bool(current_state.get("include_workshop")) == bool(include_workshop)
        ):
            logger.debug(
                "Launch runtime link check reused in-memory sync state for profile %s (include_workshop=%s)",
                normalized_profile_id,
                include_workshop,
            )
            self._last_runtime_link_sync_result = {"profile_id": normalized_profile_id, "status": "noop"}
            return True
        return self._sync_runtime_links_for_profile(normalized_profile_id, include_workshop=include_workshop)

    @staticmethod
    def _profile_update_requires_rebootstrap(data: Dict[str, Any] | None) -> bool:
        changed_keys = {
            str(key or "").strip()
            for key in ((data or {}).keys())
            if str(key or "").strip()
        }
        return bool(changed_keys & {"game_install_path", "user_data_path"})

    def _refresh_active_profile_context_after_update(self, profile_id: str, data: Dict[str, Any] | None = None) -> str:
        """
        当前激活环境更新后的后端收口。

        - 路径类变更：继续走完整 `_bootstrap_context()`，因为 scanner / load order / 日志路径都可能变化；
        - 运行态/元数据变更：只刷新当前 ProfileContext 与相关 manager 的 context，避免重建整套对象。
        """
        normalized_profile_id = str(profile_id or "").strip()
        if not normalized_profile_id:
            return "noop"

        if self._profile_update_requires_rebootstrap(data):
            self._bootstrap_context(normalized_profile_id)
            return "rebootstrap"

        refreshed_context = self.profile_mgr.activate_profile(normalized_profile_id)
        self.active_context = refreshed_context

        if self.scanner:
            self.scanner.context = refreshed_context
        if self.load_order_mgr:
            self.load_order_mgr.context = refreshed_context
        if self.game_log_mgr:
            self.game_log_mgr.context = refreshed_context
        if self.sorter:
            self.sorter.context = refreshed_context
            if getattr(self.sorter, "rule_mgr", None):
                self.sorter.rule_mgr.context = refreshed_context

        return "light"

    def _launch_profile_with_runtime_links(
        self,
        profile_id: str,
        game_install_path: str,
        extra_args: list[str] | None = None,
        include_workshop: bool = True,
    ):
        """
        直启相关分支的统一入口。
        作用：
        1. 先把本地 Mods 链接收敛到当前环境需要的状态。
        2. 再启动游戏，并由游戏监视器在确认进程出现后记录最后启动时间。
        这样可以避免多个启动分支重复维护同一段流程。
        """
        self._ensure_runtime_links_for_launch(profile_id, include_workshop=include_workshop)
        game_monitor = getattr(self, "game_monitor", None)
        if game_monitor:
            game_monitor.launch_profile_id = profile_id
        self.game_mgr.launch_game(game_install_path=game_install_path, custom_args=extra_args or [])

    def _build_direct_launch_confirmation(
        self,
        profile_id: str,
        steam_running: bool,
        reason: str,
        message: str,
        requires_fallback_confirm: bool = False,
        steam_status: dict | None = None,
    ):
        """统一构造“改为游戏本体直启”的确认响应。"""
        return ApiResponse.warning(
            message,
            data={
                "action": "confirm_direct_launch",
                "profile_id": profile_id,
                "steam_running": bool(steam_running),
                "reason": str(reason or "").strip(),
                "requires_fallback_confirm": bool(requires_fallback_confirm),
                "steam_status": steam_status or {},
            },
        )

    def _attach_steam_user_hint(self, steam_status: dict | None, waiting: bool = False) -> dict:
        """
        给 Steam 状态补上统一的人类可读提示。
        多个 API 都会直接把这个结构透传给前端，因此统一在这里处理更易维护。
        """
        status = dict(steam_status or {})
        status["user_hint"] = self._describe_steam_status(status, waiting=waiting)
        return status

    def _ensure_steam_ready(self, timeout_seconds: float = 45.0):
        """
        确保 Steam 已启动并进入已登录可用状态。
        返回: (ok, status, message)
        """
        try:
            steam_status = self.steam_mgr.get_steam_client_status()
            if steam_status.get("ready"):
                ready_status = self._attach_steam_user_hint(steam_status)
                ready_status["reason"] = "ready"
                return True, ready_status, ""

            start_result = self.steam_mgr.start_steam()
            if not start_result.get("ok"):
                failed_status = self._attach_steam_user_hint(steam_status)
                failed_status["reason"] = "steam_start_failed"
                failed_status["start_result"] = start_result
                return False, failed_status, "无法自动启动 Steam 客户端，请检查 Steam 路径配置或系统协议关联。"

            deadline = time.time() + max(1.0, float(timeout_seconds or 0))
            while time.time() < deadline:
                steam_status = self.steam_mgr.get_steam_client_status()
                if steam_status.get("ready"):
                    ready_status = self._attach_steam_user_hint(steam_status)
                    ready_status["reason"] = "ready"
                    ready_status["start_result"] = start_result
                    return True, ready_status, ""
                time.sleep(1.0)

            steam_status = self.steam_mgr.get_steam_client_status()
            timeout_status = self._attach_steam_user_hint(steam_status, waiting=True)
            timeout_status["reason"] = "steam_ready_timeout"
            timeout_status["start_result"] = start_result
            return False, timeout_status, "Steam 已尝试自动启动，但未能在限定时间内进入已登录可用状态。您可以继续改为游戏本体直启，或先确认 Steam 已登录后重试。"
        except Exception as e:
            logger.error(f"Ensure Steam ready failed: {e}", exc_info=True)
            failed_status = {
                "running": False,
                "logged_in": False,
                "ready": False,
                "reason": "steam_status_probe_failed",
                "detail": str(e),
            }
            return False, self._attach_steam_user_hint(failed_status), f"检测 Steam 状态失败: {e}。您可以继续改为游戏本体直启，或稍后重试。"

    @staticmethod
    def _describe_steam_status(steam_status: dict | None, waiting: bool = False) -> dict:
        """
        将 Steam 状态转换为统一的人类可读描述，供多个入口复用。
        """
        status = steam_status or {}
        running = bool(status.get("running"))
        logged_in = bool(status.get("logged_in"))
        ready = bool(status.get("ready"))
        detail = str(status.get("detail") or "")

        if ready:
            return {
                "state": "ready",
                "title": "Steam 已就绪",
                "message": "Steam 客户端已启动并完成登录，可以继续执行当前操作。",
            }

        if not running or detail in {"steamworks_not_running", "process_only"}:
            return {
                "state": "not_running",
                "title": "Steam 未运行",
                "message": "未检测到 Steam 客户端运行，请检查 Steam 路径配置或手动启动 Steam。",
            }

        if running and not logged_in:
            return {
                "state": "not_logged_in",
                "title": "Steam 未登录",
                "message": "Steam 客户端已启动，但尚未完成登录。请先在 Steam 中登录账号后再继续。",
            }

        if waiting:
            return {
                "state": "waiting_ready",
                "title": "等待 Steam 就绪",
                "message": "Steam 已启动，正在等待客户端进入可用状态。若长时间无响应，请确认 Steam 是否卡在登录或初始化界面。",
            }

        return {
            "state": "unknown",
            "title": "Steam 状态未知",
            "message": "Steam 当前状态无法准确判定，请稍后重试；若问题持续，可检查 Steam 登录状态和客户端完整性。",
        }

    @log_api_call
    def game_launch_resolve_warning(self, profile_id: str, action: str):
        """
        处理“直接启动且 Steam 已运行”时的用户决策。
        """
        try:
            if not profile_id:
                return ApiResponse.error("未指定 Profile ID")
            normalized_action = str(action or '').strip().lower()
            if normalized_action not in {item.value for item in LaunchWarningAction}:
                return ApiResponse.error("无效的启动确认动作")
            if normalized_action == LaunchWarningAction.CANCEL.value:
                return ApiResponse.warning("已取消启动")

            profile = self.profile_mgr.get_profile(profile_id)
            extra_args = self.profile_mgr.get_launch_args(profile_id, include_executable=False)

            if normalized_action == LaunchWarningAction.WAIT_STEAM_EXIT.value:
                steam_running = self.steam_mgr.is_steam_running()
                if steam_running:
                    return ApiResponse.warning(
                        "Steam 仍在运行，继续等待其退出。",
                        data={
                            "action": LaunchWarningAction.WAIT_STEAM_EXIT.value,
                            "profile_id": profile_id,
                            "steam_running": True,
                        },
                    )
                self._launch_profile_with_runtime_links(
                    profile_id,
                    profile.game_install_path,
                    extra_args,
                    include_workshop=True,
                )
                return ApiResponse.success(message="Steam 已退出，游戏已自动启动。")

            if normalized_action == LaunchWarningAction.CLEAR_WORKSHOP.value:
                self._launch_profile_with_runtime_links(
                    profile_id,
                    profile.game_install_path,
                    extra_args,
                    include_workshop=False,
                )
                return ApiResponse.success(message="已删除 Workshop 链接并启动游戏")
            else:
                steam_running = self.steam_mgr.is_steam_running()
                if not steam_running:
                    self._launch_profile_with_runtime_links(
                        profile_id,
                        profile.game_install_path,
                        extra_args,
                        include_workshop=True,
                    )
                    return ApiResponse.success(message="已继续直接启动游戏")

            self._launch_profile_with_runtime_links(
                profile_id,
                profile.game_install_path,
                extra_args,
                include_workshop=True,
            )
            return ApiResponse.success(message="已继续直接启动游戏")
        except Exception as e:
            logger.error(f"Resolve launch warning failed: {e}", exc_info=True)
            return ApiResponse.error(f"处理启动确认失败: {e}")

    @log_api_call
    def steam_process_status(self):
        """仅返回 Steam 进程状态，供等待 Steam 完全退出时轮询。"""
        try:
            running = bool(self.steam_mgr.is_steam_running())
            return ApiResponse.success({"running": running})
        except Exception as e:
            logger.error(f"Get Steam process status failed: {e}", exc_info=True)
            return ApiResponse.error(f"获取 Steam 进程状态失败: {e}")

    @log_api_call
    def steam_client_status(self):
        """获取 Steam 客户端当前状态。"""
        try:
            return ApiResponse.success(self._attach_steam_user_hint(self.steam_mgr.get_steam_client_status()))
        except Exception as e:
            logger.error(f"Get Steam status failed: {e}", exc_info=True)
            return ApiResponse.error(f"获取 Steam 状态失败: {e}")

    @log_api_call
    def profile_create_desktop_shortcut(self, profile_id: str):
        """为指定环境创建桌面快捷方式。"""
        try:
            if not profile_id: return ApiResponse.error("未指定 Profile ID")

            profile = self.profile_mgr.get_profile(profile_id)
            check_install = PathChecker.check_install_path(profile.game_install_path)
            check_data = PathChecker.check_normal_path(profile.user_data_path)
            if not check_install.get('pass') or not check_data.get('pass'):
                msg = f"{check_install.get('msg', '')}\n{check_data.get('msg', '')}".strip()
                return ApiResponse.error(msg or "环境路径无效，无法创建快捷方式")

            runtime_caps = self._resolve_profile_runtime_caps_from_profile(profile)
            prefer_steam_launch = bool(runtime_caps.get('steam_launch_enabled'))
            default_profile = self.profile_mgr.get_profile('default')
            same_install_as_default = os.path.normcase(os.path.normpath(profile.game_install_path)) == os.path.normcase(os.path.normpath(default_profile.game_install_path))
            steam_path_valid = bool(
                settings.config.steam_path
                and PathChecker.check_steam_path(settings.config.steam_path).get('pass', False)
            )
            effective_steam_shortcut = bool(prefer_steam_launch and steam_path_valid)
            if effective_steam_shortcut:
                extra_args = self.profile_mgr.get_launch_args(profile_id, include_executable=False)
                if same_install_as_default and bool(runtime_caps.get('is_steam_managed')):
                    shortcut = self.file_mgr.create_profile_desktop_shortcut(
                        profile=profile,
                        extra_args=extra_args,
                        prefer_steam_launch=True,
                        steam_exe_path=self.steam_mgr.steam_exe,
                        steam_app_id=RIMWORLD_APP_ID,
                    )
                    self.file_mgr.remove_existing_shortcut_variants(shortcut.get("shortcut_path", ""))
                    launch_mode = "Steam 官方 AppID"
                    return ApiResponse.success(
                        data={
                            "profile_id": profile_id,
                            "shortcut_path": shortcut.get("shortcut_path"),
                            "target_path": shortcut.get("target_path"),
                            "arguments": shortcut.get("arguments", ""),
                            "launch_mode": launch_mode,
                            "steam_path_valid": steam_path_valid,
                            "shortcut_kind": shortcut.get("shortcut_kind", "lnk"),
                        },
                        message=f"已在桌面创建环境快捷方式（{launch_mode}）",
                    )
                return ApiResponse.warning(
                    "当前环境需要先注册 Steam 非 Steam 游戏条目，再由前端按流程等待 Steam 退出、写入配置并在 Steam 启动后确认稳定快捷方式 ID。",
                    data={
                        "profile_id": profile_id,
                        "launch_mode": "Steam VDF",
                        "steam_path_valid": steam_path_valid,
                        "shortcut_kind": "steam_vdf_flow_required",
                    },
                )

            shortcut = self.file_mgr.create_profile_desktop_shortcut(
                profile=profile,
                extra_args=self.profile_mgr.get_launch_args(profile_id, include_executable=False),
                prefer_steam_launch=False,
                steam_exe_path=self.steam_mgr.steam_exe,
                steam_app_id=RIMWORLD_APP_ID,
            )
            self.file_mgr.remove_existing_shortcut_variants(shortcut.get("shortcut_path", ""))
            launch_mode = "游戏本体"
            return ApiResponse.success(
                data={
                    "profile_id": profile_id,
                    "shortcut_path": shortcut.get("shortcut_path"),
                    "target_path": shortcut.get("target_path"),
                    "arguments": shortcut.get("arguments", ""),
                    "launch_mode": launch_mode,
                    "steam_path_valid": steam_path_valid,
                    "shortcut_kind": shortcut.get("shortcut_kind", "lnk"),
                },
                message=(
                    f"当前未检测到有效 Steam 路径，已回退为环境快捷方式（{launch_mode}）"
                    if prefer_steam_launch and not steam_path_valid
                    else f"已在桌面创建环境快捷方式（{launch_mode}）"
                ),
            )
        except Exception as e:
            logger.error(f"Create Profile Shortcut Error: {e}", exc_info=True)
            return ApiResponse.error(f"创建环境快捷方式时出错: {e}")

    @log_api_call
    def profile_register_steam_shortcut(self, profile_id: str):
        """为异路径 Steam 环境写入/更新 shortcuts.vdf 条目。"""
        try:
            if not profile_id:
                return ApiResponse.error("未指定 Profile ID")

            profile = self.profile_mgr.get_profile(profile_id)
            runtime_caps = self._resolve_profile_runtime_caps_from_profile(profile)
            prefer_steam_launch = bool(runtime_caps.get('steam_launch_enabled'))
            if not prefer_steam_launch:
                return ApiResponse.error("当前环境未启用 Steam 启动，无需注册 Steam 快捷方式")

            default_profile = self.profile_mgr.get_profile('default')
            same_install_as_default = os.path.normcase(os.path.normpath(profile.game_install_path)) == os.path.normcase(os.path.normpath(default_profile.game_install_path))
            if same_install_as_default and bool(runtime_caps.get('is_steam_managed')):
                return ApiResponse.error("当前环境与默认环境使用同一游戏本体，无需注册 Steam 非 Steam 快捷方式")

            log_probe = self.steam_mgr.get_shortcut_log_probe(
                profile=profile,
                extra_args=self.profile_mgr.get_launch_args(profile_id, include_executable=False),
            )
            result = self.steam_mgr.register_profile_non_steam_shortcut(
                profile=profile,
                extra_args=self.profile_mgr.get_launch_args(profile_id, include_executable=False),
            )
            result["log_probe"] = log_probe
            return ApiResponse.success(result, message="已写入 Steam 快捷方式配置")
        except Exception as e:
            logger.error(f"Register Steam shortcut Error: {e}", exc_info=True)
            return ApiResponse.error(f"写入 Steam 快捷方式配置失败: {e}")

    @log_api_call
    def profile_finalize_steam_shortcut(self, profile_id: str, log_probe: dict | None = None):
        """
        在 Steam 完全启动后静默等待稳定 ID，并创建桌面 `.url` 快捷方式。
        设计原则：
        1. “Steam 已启动但尚未产生日志中的 shortcut appid”属于正常处理中间态，不应反复抛 warning。
        2. 由后端内部负责等待与轮询，前端只展示步骤状态，避免 toast/日志刷屏。
        3. 仅在最终超时后才向前端返回 warning。
        """
        try:
            if not profile_id:
                return ApiResponse.error("未指定 Profile ID")

            profile = self.profile_mgr.get_profile(profile_id)
            timeout_seconds = 60.0
            poll_interval_seconds = 1.0
            deadline = time.time() + timeout_seconds
            shortcut_status = {}
            launch_url = ''

            while time.time() < deadline:
                shortcut_status = self.steam_mgr.get_registered_profile_non_steam_shortcut(profile, log_probe=log_probe)
                launch_url = str(shortcut_status.get("launch_url") or '').strip()
                if launch_url:
                    break
                logger.debug(
                    "等待 Steam 生成稳定快捷方式 ID: profile=%s, user=%s, index=%s, appid=%s, source=%s",
                    profile_id,
                    shortcut_status.get("user_id"),
                    shortcut_status.get("entry_index"),
                    shortcut_status.get("appid"),
                    shortcut_status.get("source"),
                )
                time.sleep(poll_interval_seconds)

            if not launch_url:
                return ApiResponse.warning(
                    "Steam 已启动，但在限定时间内仍未生成可用的快捷方式 ID。可稍后重试，或检查 Steam 自定义游戏列表手动生成桌面快捷方式。",
                    data={
                        **shortcut_status,
                        "timeout_seconds": timeout_seconds,
                    },
                )

            game_exe = GameManager.detect_executable(profile.game_install_path) or ""
            shortcut = self.file_mgr.create_profile_desktop_url_shortcut(
                profile=profile,
                launch_url=launch_url,
                icon_location=game_exe,
            )
            self.file_mgr.remove_existing_shortcut_variants(shortcut.get("shortcut_path", ""))
            return ApiResponse.success(
                data={
                    **shortcut_status,
                    "profile_id": profile_id,
                    "shortcut_path": shortcut.get("shortcut_path"),
                    "url": launch_url,
                    "shortcut_kind": shortcut.get("shortcut_kind", "url"),
                },
                message="已创建 Steam 桌面快捷方式",
            )
        except Exception as e:
            logger.error(f"Finalize Steam shortcut Error: {e}", exc_info=True)
            return ApiResponse.error(f"确认 Steam 快捷方式失败: {e}")
    

    # =========================================================================
    #  6. 文件与资源操作 (Files & Assets)
    # =========================================================================

    @log_api_call
    def path_check(self, path_type, path):
        """
        检查指定路径类型是否正确
        :param path_type: 路径类型（game_install_path, game_config_path, workshop_mods_path, steam_path）
        :param path: 路径字符串
        """
        if not path_type or not path:
            return ApiResponse.error("未指定路径类型或路径")
        try:
            if path_type == "game_install_path":
                res = PathChecker.check_install_path(path)
            elif path_type == "game_config_path":
                res = PathChecker.check_mods_config(path)
            elif path_type == "workshop_mods_path":
                res = PathChecker.check_workshop_path(path)
            elif path_type == "user_data_path":
                res = PathChecker.check_user_data_path(path)
            elif path_type == "steam_path":
                res = PathChecker.check_steam_path(path)
            elif path_type == "steamcmd_path":
                res = PathChecker.check_steamcmd_path(path)
            elif path_type == "texture_tools_path":
                res = PathChecker.check_texture_tools_path(path)
            else:
                res = PathChecker.check_normal_path(path)
                
        except Exception as e:
            return ApiResponse.error(f"检查路径时出错: {e}")
        
        return ApiResponse.success(res)
        
    @log_api_call
    def paths_check(self, paths_data: dict):
        """
        检查多个路径是否正确
        :param paths_data: 包含路径类型和路径字符串的字典
        """
        if not paths_data:
            return ApiResponse.error("未指定任何路径信息")
        info = {}
        try:
            info = PathChecker.paths_check(paths_data)
            return ApiResponse.success(info)
        except Exception as e:
            logger.error(f"Check Paths Error: {e}", exc_info=True)
            return ApiResponse.error(f"检查路径时出错: {e}")
    
    @log_api_call
    def path_open(self, path: str):
        try:
            file_mgr.open_in_explorer(path)
            logger.info(f"打开路径: {path}")
            return ApiResponse.success()
        except Exception as e:
            logger.error(f"打开路径时出错: {e}", exc_info=True)
            return ApiResponse.error(f"打开路径时出错: {e}")

    @log_api_call
    def path_open_file(self, path: str):
        try:
            file_mgr.open_file(path)
            logger.info(f"打开文件: {path}")
            return ApiResponse.success()
        except Exception as e:
            logger.error(f"打开文件时出错: {e}", exc_info=True)
            return ApiResponse.error(f"打开文件时出错: {e}")

    @log_api_call
    def path_read_text_file(self, path: str, max_bytes: int = 2 * 1024 * 1024):
        try:
            data = file_mgr.read_text_file(path, max_bytes=max_bytes)
            return ApiResponse.success(data)
        except Exception as e:
            logger.error(f"读取文本文件时出错: {e}", exc_info=True)
            return ApiResponse.error(f"读取文本文件时出错: {e}")
    
    @log_api_call
    def path_delete(self, path: str, force: bool = False):
        """删除文件/文件夹"""
        try:
            res = self._delete_paths(path, force=force)
            if res['paths'] and res['success_count'] <= 0 and not res['errors']:
                return ApiResponse.warning("路径不存在或无法删除", data=res)
            return self._build_delete_response("路径", 1 if res['paths'] else 0, res)
        except Exception as e:
            return ApiResponse.error(f"删除路径时出错: {e}")
    
    @log_api_call
    def paths_delete(self, paths: List[str], force: bool = False):
        """批量删除文件/文件夹"""
        try:
            res = self._delete_paths(paths, force=force)
            return self._build_delete_response("路径", len(res['paths']), res)
        except Exception as e:
            return ApiResponse.error(f"批量删除路径时出错: {e}")
    
    @log_api_call
    def folder_select_dialog(self, initial_dir: str = ''):
        """
        打开系统原生的文件夹选择框
        """
        try:
            folder = file_mgr.select_folder_dialog(initial_dir)
            if folder: return ApiResponse.success(folder)
        except Exception as e:
            return ApiResponse.error(f"选择文件夹时出错: {e}")
        return ApiResponse.warning("未选择文件夹")
    
    @log_api_call
    def file_select_dialog(
        self,
        initial_dir: str = '',
        file_types = (
            'Load Order Files (*.xml;*.rws;*.rml;*.json;*.txt;*.list)',
            'All Files (*.*)',
        ),
    ):
        """
        打开系统原生的文件选择框
        """
        try:
            file = file_mgr.select_file_dialog(initial_dir, file_types)
            if file: return ApiResponse.success(file)
        except Exception as e:
            return ApiResponse.error(f"选择文件时出错: {e}")
        return ApiResponse.warning("未选择文件")

    @log_api_call
    def file_save_dialog(
        self,
        initial_dir: str = '',
        default_filename: str = 'output.xml',
        file_types = ('XML Files (*.xml)', 'RML Files (*.rml)', 'All Files (*.*)'),
    ):
        """
        打开系统原生的文件保存框
        """
        try:
            file = file_mgr.save_file_dialog(initial_dir, default_filename, file_types)
            if file: return ApiResponse.success(file)
        except Exception as e:
            return ApiResponse.error(f"保存文件时出错: {e}")
        return ApiResponse.warning("未选择文件")

    @log_api_call
    def search_files_start(self, payload: dict):
        if not self.file_search_mgr:
            return ApiResponse.error("文件搜索管理器未初始化")
        try:
            task_id = self.file_search_mgr.start_search(payload)
            return ApiResponse.success({"task_id": task_id}, message="搜索任务已启动")
        except Exception as e:
            logger.error(f"启动文件搜索失败: {e}", exc_info=True)
            return ApiResponse.error(f"启动文件搜索失败: {e}")
    
    @log_api_call
    def localize_workshop_mods(self, path_hashes: List[str], store: str = 'workshop'):
        """
        将指定副本转为本地模组，并推送实时进度。
        这里使用 path_hash 精确定位副本，避免共存场景下 workshop_id/package_id 指向不唯一。
        """
        cfg = settings.config
        local_root = self.active_context.local_mods_path if self.active_context else ""
        if not local_root: return ApiResponse.error("未指定本地模组路径")

        normalized_hashes = [str(item or "").strip() for item in path_hashes if str(item or "").strip()]
        if not normalized_hashes:
            return ApiResponse.warning(f"没有可转换的{store}模组")

        # 1. 准备任务 (使用 JOIN 一次性查出所有需要的数据)
        # 使用 path_hash 锁定当前副本，避免共存副本间串改。
        query = (ModAsset.select(ModAsset, UserModData.alias_name)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
            .where(ModAsset.path_hash << normalized_hashes, ModAsset.store == store) # type: ignore
            .dicts())
        try:
            # 2. 执行任务
            res = file_mgr.localize_workshop_mods(query, local_root, cfg.coexist_mod_folder_name_type)
            if not res: return ApiResponse.warning(f"没有可转换的{store}模组")
        except Exception as e:
            logger.error(f"Localize workshop mods failed: {e}", exc_info=True)
            return ApiResponse.error(f"本地化任务失败: {str(e)}")
        
        return ApiResponse.success({"task_id": res}, message="本地化任务已在后台启动")
    
    @log_api_call
    def workspace_transfer_mods(self, path_hashes: list, target_store: str, mode: str = 'copy'):
        """
        跨库转移模组 (复制 / 移动)
        :param target_store: 'local' 或 'self'
        :param mode: 'copy' 或 'move'
        """
        if not self.active_context: return ApiResponse.error("未指定环境")
        # 1. 拦截非法目标
        # if target_store == 'workshop':
        #     return ApiResponse.error("为了保证 Steam 同步机制不被破坏，禁止手动向创意工坊目录导入文件。")
        # 2. 确定目标根目录
        target_root = ""
        if target_store == 'local':
            target_root = self.active_context.local_mods_path
        elif target_store == 'self':
            target_root = settings.config.self_mods_path
        elif target_store == 'workshop':
            target_root = settings.config.workshop_mods_path
        if not target_root or not os.path.exists(target_root):
            return ApiResponse.error(f"目标库 {target_store} 的目录未配置或不存在！")
        # 3. 查出源文件信息
        from backend.database.models import ModAsset
        source_mods = ModAsset.select(ModAsset.path_hash, ModAsset.path, ModAsset.package_id, ModAsset.store, ModAsset.name).where(ModAsset.path_hash.in_(path_hashes)).dicts() # type: ignore
        source_mods = list(source_mods)
        if not source_mods: return ApiResponse.error("未找到指定的源文件")
        # 4. 执行物理操作
        import shutil
        success_count = 0
        errors = []
        # 确定文件夹命名策略
        name_strategy = settings.config.coexist_mod_folder_name_type
        for mod in source_mods:
            src_path = mod['path']
            # 防御：禁止对工坊项目执行 Move 操作
            current_mode = mode
            if mod['store'] == 'workshop' and mode == 'move':
                current_mode = 'copy' # 强制降级为复制
            # 生成目标文件夹名称
            # 策略：如果是去 Local，遵循命名设置；如果是去 Self，且有 workshop_id，最好以 ID 命名
            if target_store == 'self' and mod.get('workshop_id'):
                folder_name = mod['workshop_id']
            else:
                # 简单处理：使用原始文件夹名。如果你想更智能，可以调用 file_mgr.generate_folder_name
                folder_name = os.path.basename(src_path)
            dst_path = os.path.join(target_root, folder_name)
            # 防止重名覆盖
            counter = 1
            while os.path.exists(dst_path):
                dst_path = os.path.join(target_root, f"{folder_name}_{counter}")
                counter += 1
            try:
                if current_mode == 'move':
                    shutil.move(src_path, dst_path)
                else:
                    shutil.copytree(src_path, dst_path)
                success_count += 1
            except Exception as e:
                errors.append(f"{mod['name']}: {str(e)}")
        
        # 物理操作完成后，同步更新数据库记录，避免前端全量扫描
        with db.atomic():
            for mod in source_mods:
                if mode == 'move':
                    # 如果是移动，更新 path 和 store
                    # 注意：path_hash 也要重新生成，因为物理路径变了
                    new_path = os.path.join(target_root, os.path.basename(mod['path']))
                    new_hash = generate_path_hash(new_path)
                    ModAsset.update(
                        path=new_path,
                        path_hash=new_hash,
                        store=target_store
                    ).where(ModAsset.path_hash == mod['path_hash']).execute()
                else:
                    # 如果是复制，直接 return success 然后让前端触发异步扫描
                    pass

        msg = f"成功转移 {success_count} 个模组。"
        if errors:
            msg += f" {len(errors)} 个失败。"
            return ApiResponse.warning(msg, data={"errors": errors})
        
        return ApiResponse.success(message=msg)
    
    
    # =========================================================================
    #  7. 排序与管理 (Sort & Rule Management)
    # =========================================================================

    @log_api_call
    def auto_sort_mods(self, active_ids: List[str]):
        """
        前端点击“自动排序”时调用
        """
        try:
            canonical_active_ids, preferred_tokens = self._canonicalize_load_order_ids(active_ids)
            result = self.sorter.sort(canonical_active_ids) if self.sorter else {}
            if not result: return ApiResponse.error("排序失败, 排序引擎未初始化")
            result["sorted_ids"] = self._restore_load_order_tokens(result.get("sorted_ids", []), preferred_tokens)
            result["auto_activated"] = self._restore_load_order_tokens(result.get("auto_activated", []), preferred_tokens)
            # result 包含: sorted_ids, auto_activated, warnings
            msg = "排序完成"
            if result.get('auto_activated'):
                msg += f" (自动激活了 {len(result['auto_activated'])} 个联锁项)"
            
            return ApiResponse.success(result, msg)
        except Exception as e:
            logger.error(f"Auto sort failed: {e}", exc_info=True)
            return ApiResponse.error(f"排序失败: {str(e)}")
    
    @log_api_call
    def smart_insert_mod_in_actives(self, package_ids: List[str], current_active_ids: List[str]):
        """
        智能插入模组到激活列表中
        前端点击“智能插入”时调用
        """
        if not package_ids or current_active_ids is None:
            return ApiResponse.error("请输入模组 ID 或当前激活列表")
        if not self.sorter:
            return ApiResponse.error("规则引擎未初始化")
        try:
            canonical_target_ids, target_token_map = self._canonicalize_load_order_ids(package_ids)
            canonical_current_ids, current_token_map = self._canonicalize_load_order_ids(current_active_ids)
            context_mods = ModDAO.get_profile_mods(self.active_context)
            mod_map = {m['package_id'].lower(): m for m in context_mods}
            final_ids = self.sorter.smart_insert_mods(canonical_target_ids, canonical_current_ids, mod_map)
            final_ids = self._restore_load_order_tokens(final_ids, {**current_token_map, **target_token_map})
            return ApiResponse.success(data=final_ids) if final_ids else ApiResponse.error("插入失败")
        except Exception as e:
            return ApiResponse.error(f"插入失败: {str(e)}")
    
    @log_api_call
    def rules_get_all(self):
        """
        获取所有规则（用于规则管理界面显示）
        前端需要完整数据来支持搜索和查看
        """
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        return ApiResponse.success({
            "community_rules": self.sorter.rule_mgr.community_rules, # 返回完整字典
            "community_rules_update_time": self.sorter.rule_mgr.community_rules_update_time,
            "workshop_rules": self.sorter.rule_mgr.get_workshop_rules(),
            "user_mod_rules": self.sorter.rule_mgr.user_mod_rules,
            "user_dynamic_rules": self.sorter.rule_mgr.user_dynamic_rules,
            "settings": self.sorter.rule_mgr.settings,
        })

    @log_api_call
    def rule_update_user_mod(self, package_id: str, rule_content: dict):
        """保存单个规则"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.update_user_mod_rule(package_id, rule_content)
            return ApiResponse.success() if success else ApiResponse.error("保存失败")
        except Exception as e:
            return ApiResponse.error(f"保存失败: {str(e)}")
    
    @log_api_call
    def rule_set_user_mod_absolute_position(self, package_id: str, position: str, comment: str = ""):
        """ position: 'top', 'bottom', 或 'none' """
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.set_user_mod_absolute_position(package_id, position, comment)
            return ApiResponse.success() if success else ApiResponse.error("保存失败")
        except Exception as e:
            return ApiResponse.error(f"保存失败: {str(e)}")
    
    @log_api_call
    def rule_delete_user_mod(self, package_id: str):
        """删除单个规则"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.delete_user_mod_rule(package_id)
            return ApiResponse.success() if success else ApiResponse.error("删除失败")
        except Exception as e:
            return ApiResponse.error(f"删除失败: {str(e)}")

    @log_api_call
    def rule_set_language_pack_owner_override(self, package_id: str, owner_ids: list[str], replace: bool = False):
        """设置语言包归属手动覆盖。"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.set_language_pack_owner_override(package_id, owner_ids, replace)
            return ApiResponse.success() if success else ApiResponse.error("保存失败")
        except Exception as e:
            return ApiResponse.error(f"保存失败: {str(e)}")
    
    @log_api_call
    def rule_get_settings(self):
        """获取规则系统的全局设置 (开关状态、黑名单等)"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        return ApiResponse.success(self.sorter.rule_mgr.settings)

    def change_rule_source_priority(self, rules_sources: List[str]):
        """
        改变规则来源的优先级
        rules_sources: 按优先级排序的规则来源列表
        """
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.change_rule_source_priority(rules_sources)
            return ApiResponse.success() if success else ApiResponse.error("设置失败")
        except Exception as e:
            return ApiResponse.error(f"设置失败: {str(e)}")
    
    @log_api_call
    def rule_global_enable(self, key: str, enabled: bool):
        """
        设置全局开关
        key: 'community_mod_rules_enabled' | 'user_mod_rules_enabled' | 'dynamic_rules_enabled'
        """
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.set_global_setting(key, enabled)
            return ApiResponse.success() if success else ApiResponse.error("设置失败：无效的 Key")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def rule_toggle_mod(self, rule_type: str, package_id: str, exclude: bool):
        """
        针对单个 Mod 禁用/启用用户自定义单项规则 (黑名单操作)
        """
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            if (rule_type == 'user'):
                success = self.sorter.rule_mgr.toggle_user_mod_rule_exclusion(package_id, exclude)
            elif (rule_type == 'community'):
                success = self.sorter.rule_mgr.toggle_community_mod_exclusion(package_id, exclude)
            elif (rule_type == 'workshop'):
                success = self.sorter.rule_mgr.toggle_workshop_mod_exclusion(package_id, exclude)
            else:
                return ApiResponse.error("操作失败：无效的 Rule Type")
            return ApiResponse.success() if success else ApiResponse.error("操作失败")
        except Exception as e:
            logger.error(f"Toggle mod rule failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))
    
    @log_api_call
    def rule_toggle_dynamic(self, rule_id: str, enabled: bool):
        """切换动态规则的启用状态"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.toggle_dynamic_rule(rule_id, enabled)
            return ApiResponse.success() if success else ApiResponse.error("切换失败")
        except Exception as e:
            return ApiResponse.error(f"切换失败: {str(e)}")
    
    @log_api_call
    def rule_update_dynamic(self, rule_obj: dict):
        """保存动态规则"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.upsert_dynamic_rule(rule_obj)
            return ApiResponse.success() if success else ApiResponse.error("保存失败")
        except Exception as e:
            return ApiResponse.error(f"保存失败: {str(e)}")

    @log_api_call
    def rule_delete_dynamic(self, rule_id: str):
        """删除动态规则"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            success = self.sorter.rule_mgr.delete_dynamic_rule(rule_id)
            return ApiResponse.success() if success else ApiResponse.error("删除失败")
        except Exception as e:
            return ApiResponse.error(f"删除失败: {str(e)}")

    @log_api_call
    def rule_export_bundle(self, dynamic_rule_ids: List[str], initial_dir: str = ''):
        """
        规则中心导出入口。
        界面保持不变，底层改为统一数据包的规则预设。
        """
        return self.data_bundle_export({
            "preset": "rules",
            "module_keys": list(DataBundleManager.RULE_PRESET),
            "dynamic_rule_ids": list(dynamic_rule_ids or []),
            "filename": f"RimModManager_Rules_{datetime.now().strftime('%Y%m%d')}{DataBundleManager.FILE_EXTENSION}",
        })

    @log_api_call
    def rule_import_bundle(self):
        """规则中心导入入口，同时兼容旧版 JSON 规则包。"""
        try:
            path = file_mgr.select_file_dialog(file_types=(
                _build_dialog_file_type_label(
                    'RMM Data Package',
                    [DataBundleManager.FILE_EXTENSION, *DataBundleManager.LEGACY_FILE_EXTENSIONS, '.json'],
                ),
                'All Files (*.*)',
            ))
            if path:
                import_result = self.data_bundle_mgr.import_bundle(
                    path,
                    module_keys=list(DataBundleManager.RULE_PRESET),
                    default_profile_mode="clone",
                )
                warnings = import_result.get("warnings", [])
                message = "规则包导入成功"
                if warnings:
                    message = f"规则包导入成功，附带 {len(warnings)} 条提示。"
                return ApiResponse.success(data=import_result, message=message)
            return ApiResponse.warning("已取消")
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            return ApiResponse.error(f"导入失败: {e}")
    
    @log_api_call
    def update_community_rule(self):
        """兼容旧入口：统一转发到外置数据更新管线。"""
        return self.update_external_db("community_rules")

    
    # =========================================================================
    #  8. 日志管理 (Log Management)
    # =========================================================================

    def get_log_files(self, log_type='game'):
        """ 获取指定类型的日志文件列表 ('app' 或 'game') """
        try:
            if log_type == 'app':
                files = app_log_reader.get_log_files()
            else:
                if not self.game_log_mgr: return ApiResponse.warning("游戏环境未就绪，无法获取游戏日志")
                files = self.game_log_mgr.get_log_files()
                
            return ApiResponse.success(files)
        except Exception as e:
            logger.error(f"Get log files failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))

    def read_log_page(self, log_type: str, filename: str, page: int = 1, page_size: int = 1000):
        """ 分页读取日志 """
        try:
            if log_type == 'app':
                result = app_log_reader.read_log_page(filename, page, page_size)
            else:
                if not self.game_log_mgr: return ApiResponse.warning("游戏环境未就绪，无法读取游戏日志")
                result = self.game_log_mgr.read_log_page(filename, page, page_size)
                
            if 'error' in result: return ApiResponse.error(result['error'])
            return ApiResponse.success(result)
        except Exception as e:
            logger.error(f"Read log page failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))
    
    @log_api_call
    def open_log_folder(self):
        """ 打开日志所在文件夹 """
        path = self.game_log_mgr.get_preferred_log_directory() if self.game_log_mgr else None
        if path and os.path.exists(path):
            file_mgr.open_in_explorer(path)
            return ApiResponse.success()
        return ApiResponse.error("日志路径不存在")
    
    
    # =========================================================================
    #  9. 网络与下载管理 (Download Management)
    # =========================================================================
    
    @log_api_call
    def download_file(self, url: str, target_dir = None, filename = None):
        """
        通用文件下载接口
        :param url: 下载链接 (支持 GitHub blob)
        :param target_dir: 目标目录 (如果不传，默认下载到 Downloads 或 Temp)
        :param filename: 重命名文件名
        """
        if not target_dir:
            # 默认下载到应用目录下的 Downloads
            target_dir = str(HOME_DIR / 'Downloads')
            os.makedirs(target_dir, exist_ok=True)
            
        task_id = self.download_mgr.add_task(url, target_dir, filename)
        return ApiResponse.success({"task_id": task_id}, "下载任务已添加")

    @log_api_call
    def cancel_progress_task(self, task_id: str, task_type: str):
        """统一取消入口，供前端全局任务栏按任务类型路由控制。"""
        normalized_task_id = str(task_id or "").strip()
        normalized_type = str(task_type or "").strip().lower()

        if normalized_type in {"download", "update"}:
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            self.download_mgr.cancel_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消下载任务")

        if normalized_type == "localize":
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = file_mgr.cancel_localize_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消本地化任务") if ok else ApiResponse.error("当前没有可取消的本地化任务")

        if normalized_type == "scan":
            if not self.scanner:
                return ApiResponse.error("扫描器未初始化")
            ok = self.scanner.stop_scan(normalized_task_id or None)
            return ApiResponse.success(message="已请求取消扫描任务") if ok else ApiResponse.error("当前没有可取消的扫描任务")

        if normalized_type in {"steamcmd-download", "steamcmd-init"}:
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = self.steam_mgr.cancel_steamcmd_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消 SteamCMD 任务") if ok else ApiResponse.error("当前没有可取消的 SteamCMD 任务")

        if normalized_type in {"steam-subscribe", "steam-unsubscribe"}:
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = self.steam_mgr.abort_monitor_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消 Steam 任务") if ok else ApiResponse.error("当前没有可取消的 Steam 任务")

        if normalized_type in {"texture-opt", "texture-opt-analyze"}:
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            try:
                res = self.texture_mgr.cancel_task(normalized_task_id)
                return ApiResponse.success(res, message="已请求取消贴图任务")
            except Exception as e:
                return ApiResponse.error(str(e))

        if normalized_type == "file-search":
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = self.file_search_mgr.cancel_task(normalized_task_id) if self.file_search_mgr else False
            return ApiResponse.success(message="已请求取消文件搜索任务") if ok else ApiResponse.error("当前没有可取消的文件搜索任务")

        if normalized_type == "ai-task":
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = self.ai_mgr.cancel_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消 AI 任务") if ok else ApiResponse.error("当前没有可取消的 AI 任务")

        if normalized_type == "mod-export":
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = self.mod_package_mgr.cancel_export_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消模组导出任务") if ok else ApiResponse.error("当前没有可取消的模组导出任务")

        if normalized_type == "mod-import":
            if not normalized_task_id:
                return ApiResponse.error("缺少任务 ID")
            ok = self.mod_package_mgr.cancel_import_task(normalized_task_id)
            return ApiResponse.success(message="已请求取消模组导入任务") if ok else ApiResponse.error("当前没有可取消的模组导入任务")

        return ApiResponse.error(f"该任务类型暂不支持取消: {normalized_type or 'unknown'}")

    @log_api_call
    def get_active_downloads(self):
        """获取所有任务状态 (用于 UI 恢复)"""
        return ApiResponse.success(self.download_mgr.get_tasks_info())
    
    @log_api_call
    def open_sub_browser(self, url='', title = 'RimModManager'):
        """打开或更新 浏览器子窗口"""
        if self.is_browser_runtime() or not self._window:
            target_url = build_sub_browser_target_url(self._browser_base_url, url, title) if self.is_browser_runtime() else str(url or "")
            if target_url:
                webbrowser.open(target_url)
            return ApiResponse.success({"url": target_url or str(url or "")})
        if not self.browser_window: 
            self.browser_window = SubBrowserManager(self)
        self.browser_window.open(url, title)
        return ApiResponse.success()

    @log_api_call
    def workshop_browser_action(self, action: str, workshop_id: str = "", target_url: str = ""):
        normalized_action = str(action or "").strip().lower()
        normalized_workshop_id = str(workshop_id or "").strip()
        normalized_target_url = str(target_url or "").strip()

        if normalized_action == "open_in_steam":
            if normalized_workshop_id:
                return self.steam_open_workshop_page(normalized_workshop_id)
            return ApiResponse.error("无法识别当前页面的 Workshop ID")

        if not normalized_workshop_id:
            return ApiResponse.error("无法识别当前页面的 Workshop ID")

        if normalized_action == "subscribe":
            return self.steam_subscribe([normalized_workshop_id])
        if normalized_action == "unsubscribe":
            return self.steam_unsubscribe([normalized_workshop_id])
        if normalized_action == "download":
            return self.steamcmd_download([normalized_workshop_id])
        if normalized_action == "open_original":
            if normalized_target_url:
                webbrowser.open(normalized_target_url)
                return ApiResponse.success(message="已在系统浏览器打开原网页")
            return ApiResponse.error("未提供目标网页地址")

        return ApiResponse.error(f"未知操作: {normalized_action}")


    # ==========================================
    #  10. 更新管理 (Updates)
    # ==========================================
    @log_api_call
    def update_check(self, manual=True):
        """
        检查版本更新
        :param manual: 是否为用户手动触发
        """
        try:
            # 1. 让管理器去聚合检查（含本地缓存检查）
            info = self.update_mgr.check_all()
            # 记录检查时间
            settings.set('last_update_check_time', current_ms())
            # 2. 自动忽略逻辑
            # 如果不是手动检查，且版本是被用户标记忽略的，且本地没有已经下载好的包
            # (如果本地已经下好了，即使是忽略版本也应该提示安装，避免浪费空间)
            ignored_ver = settings.config.ignored_update_version
            if not manual and info.version == ignored_ver and info.local_status != 'ready':
                return ApiResponse.success({ "has_update": False })
            # 3. 返回给前端
            # info.to_dict() 包含了 local_status ('remote'|'downloading'|'ready')
            return ApiResponse.success(info.to_dict())
        except Exception as e:
            logger.error(f"Check update failed: {e}", exc_info=True)
            return ApiResponse.error(f"检查更新失败: {str(e)}")

    @log_api_call
    def update_trigger_action(self):
        """
        [统一入口] 触发更新操作
        根据当前状态，自动决定是 '开始下载' 还是 '直接安装'
        """
        try:
            # 获取当前缓存的更新信息
            info = self.update_mgr.current_update_info
            if not info or not info.has_update:
                return ApiResponse.error("当前没有可用的更新信息，请先检查更新")
            # A. 如果本地已就绪 -> 执行安装
            if info.local_status == "ready":
                self.update_mgr.execute_hot_swap() # 这会重启程序
                return ApiResponse.success(message="正在重启进行安装...")
            # B. 否则 -> 开始下载
            else:
                result = self.update_mgr.perform_update_download()
                # result 格式: {"status": "downloading", "task_id": "..."}
                return ApiResponse.success(result, message="开始下载更新包")
                
        except Exception as e:
            logger.error(f"Update action failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))

    @log_api_call
    def update_ignore_version(self, version_str):
        """跳过当前版本"""
        settings.set('ignored_update_version', version_str)
        return ApiResponse.success()

    @log_api_call
    def maintenance_check_tools(self):
        """检查外部工具环境状态，不自动下载。"""
        try:
            checked = self.maintenance_mgr.check_tools()
            checked_at = int(checked.get("checked_at") or current_ms())
            settings.set("last_tool_check_time", checked_at)
            return ApiResponse.success(checked)
        except Exception as e:
            logger.error("Check tools maintenance failed: %s", e, exc_info=True)
            return ApiResponse.error(f"检查工具环境失败: {e}")

    @log_api_call
    def maintenance_check_external_data(self):
        """检查社区规则/数据库等外部文件是否需要更新。"""
        try:
            checked = self.maintenance_mgr.check_external_data()
            checked_at = int(checked.get("checked_at") or current_ms())
            items = checked.get("items") if isinstance(checked, dict) else []
            failed = checked.get("failed") if isinstance(checked, dict) else []
            items = items if isinstance(items, list) else []
            failed = failed if isinstance(failed, list) else []
            # 整轮远端状态都没拿到时，不刷新“上次成功检查时间”，避免自动检查被失败结果错误限流。
            if not items or len(failed) < len(items):
                settings.set("last_external_data_update_check_time", checked_at)
            return ApiResponse.success(checked)
        except Exception as e:
            logger.error("Check external data maintenance failed: %s", e, exc_info=True)
            return ApiResponse.error(f"检查外部库更新失败: {e}")

    @log_api_call
    def maintenance_check_steamcmd_mod_updates(self):
        """仅检查 SteamCMD 管理目录中的工坊模组更新。"""
        try:
            checked = self.maintenance_mgr.check_steamcmd_mod_updates()
            checked_at = int(checked.get("checked_at") or current_ms())
            settings.set("last_steamcmd_mod_update_check_time", checked_at)
            return ApiResponse.success(checked)
        except Exception as e:
            logger.error("Check SteamCMD mod updates failed: %s", e, exc_info=True)
            return ApiResponse.error(f"检查 SteamCMD 模组更新失败: {e}")
    
    
    # =========================================================================
    #  11. Steam 集成 (Steam Integration)
    # =========================================================================

    @log_api_call
    def check_steam_tools(self):
        """
        兼容旧接口：仅返回 SteamCMD 当前状态，不再自动触发下载。
        """
        return ApiResponse.success({
            "steamcmd_ready": self.steam_mgr.steamcmd_ready,
            "pending_tasks": [],
            "status": self.maintenance_mgr.check_tools(),
        })

    @log_api_call
    def steam_tools_install(self):
        """用户确认后调用：按需下载并初始化 SteamCMD。"""
        tasks = self.steam_mgr.ensure_tools(self.download_mgr)
        if tasks:
            threading.Thread(target=self._monitor_setup_tasks, args=(tasks,), daemon=True).start()
        return ApiResponse.success({
            "steamcmd_ready": self.steam_mgr.steamcmd_ready,
            "pending_tasks": tasks,
        })

    def _monitor_setup_tasks(self, tasks):
        """(内部) 监控工具下载任务，完成后只负责执行解压/部署。"""
        import time
        from backend.managers.mgr_download import TaskStatus
        
        pending = list(tasks)
        while pending:
            time.sleep(1)
            for item in pending[:]:
                task_id = item['id']
                task_type = item['type']
                
                # 从 DownloadManager 获取状态
                task = self.download_mgr.tasks.get(task_id)
                if not task: continue
                
                if task.status == TaskStatus.COMPLETED:
                    # 执行解压或移动
                    self.steam_mgr.post_download_setup(task_type, task.dest_path)
                    pending.remove(item)
                elif task.status == TaskStatus.ERROR:
                    logger.error(f"Setup task failed: {task_id}", exc_info=True)
                    pending.remove(item)

    @log_api_call
    def steam_subscribe(self, workshop_ids: str|list[str]):
        """调用 Steam 客户端订阅"""
        try:
            ok, steam_status, message = self._ensure_steam_ready(timeout_seconds=45)
            if not ok:
                return ApiResponse.warning(message, data={"action": "steam_not_ready", "steam_status": steam_status})
            success = self.steam_mgr.subscribe_items(workshop_ids)
            if success:
                return ApiResponse.success(message="已发送订阅请求 (需Steam运行中)")
            else:
                return ApiResponse.error("操作失败：SteamAPI 未就绪 (请确保Steam已运行)")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def steam_unsubscribe(self, workshop_ids: str|list[str]):
        """调用 Steam 客户端取消订阅"""
        try:
            ok, steam_status, message = self._ensure_steam_ready(timeout_seconds=45)
            if not ok:
                return ApiResponse.warning(message, data={"action": "steam_not_ready", "steam_status": steam_status})
            success = self.steam_mgr.unsubscribe_items(workshop_ids)
            if success:
                return ApiResponse.success(message="已发送取消订阅请求")
            else:
                return ApiResponse.error("操作失败：SteamAPI 未就绪")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def steam_launch_client(self):
        """前端主动调用唤醒 Steam"""
        ok, steam_status, message = self._ensure_steam_ready(timeout_seconds=45)
        if ok:
            return ApiResponse.success(data=steam_status, message="Steam 客户端已启动并进入可用状态。")
        return ApiResponse.warning(message, data={"action": "steam_not_ready", "steam_status": steam_status})

    @log_api_call
    def steam_open_workshop_page(self, workshop_id: str):
        """在 Steam 客户端中打开指定工坊页面"""
        normalized_id = str(workshop_id or "").strip()
        if not normalized_id:
            return ApiResponse.error("未提供有效的 Workshop ID")
        steam_url = f"steam://url/CommunityFilePage/{normalized_id}"
        try:
            if webbrowser.open(steam_url):
                return ApiResponse.success(message="已尝试在 Steam 客户端打开当前页面")
        except Exception as e:
            logger.warning(f"Open workshop in Steam failed: {e}")
        return ApiResponse.error("无法在 Steam 客户端中打开当前页面")
    
    @log_api_call
    def steam_check_status(self, workshop_id: str):
        """
        检查 Mod 是否已在 Steam 客户端完成安装
        """
        try:
            wid = int(workshop_id)
            is_installed = self.steam_mgr.is_subscribed(wid)
            return ApiResponse.success({"is_installed": is_installed})
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def steamcmd_download(self, workshop_ids: list):
        """
        使用 SteamCMD 下载/更新 Mod
        """
        try:
            if not self.steam_mgr.steamcmd_ready:
                return ApiResponse.error("SteamCMD 未安装，正在尝试自动修复，请稍后...")
            
            # 启动后台下载
            self.steam_mgr.download_workshop_items(workshop_ids, on_success=lambda: self.scan_mods())
            return ApiResponse.success(message="SteamCMD 下载任务已启动")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    # =========================================================================
    #  12. AI 功能 (AI Features)
    # =========================================================================

    
    @log_api_call
    def ai_get_config(self):
        """获取当前 AI 配置和模板列表"""
        from backend.settings import AIConfig
        ai_cfg = settings.config.ai
        # 如果是字典，先转成对象，方便统一调用 asdict
        if isinstance(ai_cfg, dict):
            ai_cfg = AIConfig(**ai_cfg)
        config_payload = asdict(ai_cfg)
        config_payload["resolved_token_budget"] = {
            "profile": ai_cfg.model_token_budget(),
            "context_window_tokens": ai_cfg.resolved_context_window_tokens(),
            "max_input_tokens": ai_cfg.resolved_max_input_tokens(),
            "max_output_tokens": ai_cfg.resolved_max_output_tokens(),
        }
        return ApiResponse.success({
            "config": config_payload,
            "prompts": self.ai_mgr.prompts,
            "assistants": self.ai_mgr.assistants,
            "tasks": self.ai_mgr.tasks,
            "definition_editor_meta": self.ai_mgr.definition_editor_meta,
            "providers": self.ai_mgr.get_providers(),
            "model_capability_meta": self.ai_mgr.get_model_capability_meta(),
        })

    @log_api_call
    def ai_save_config(self, config_data: dict):
        """保存 AI 配置"""
        try:
            current_ai = settings.config.ai
            editable_keys = {
                "enabled",
                "provider",
                "endpoint_mode",
                "base_url",
                "api_key",
                "model",
                "temperature",
                "max_output_tokens",
                "max_input_tokens",
                "context_window_tokens",
                "max_concurrency",
            }
            for k, v in (config_data or {}).items():
                if k not in editable_keys or not hasattr(current_ai, k):
                    continue
                setattr(current_ai, k, v)

            settings.save()
            return ApiResponse.success(message="AI 配置已保存")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_check_enable(self):
        """检查 AI 功能是否启用"""
        return self._ai_check_enable_with_config()

    def _ai_check_enable_with_config(self, override_config: dict | None = None):
        """检查 AI 功能是否启用，并支持用临时配置覆盖当前设置。"""
        from backend.settings import AIConfig

        ai_cfg = settings.config.ai
        if isinstance(ai_cfg, dict):
            ai_cfg = AIConfig(**ai_cfg)

        if override_config:
            merged = asdict(ai_cfg)
            for key, value in override_config.items():
                if key in merged:
                    merged[key] = value
            ai_cfg = AIConfig(**merged)

        if not ai_cfg.enabled:
            return ApiResponse.error("AI 功能未启用，请前往设置开启。")

        from backend.ai.ai_gateway import validate_ai_connection_config
        ok, message = validate_ai_connection_config(ai_cfg)
        if not ok:
            return ApiResponse.error(message)

        return ApiResponse.success()

    @log_api_call
    def ai_get_providers(self):
        """获取厂商或代理协议列表"""
        try:
            providers = self.ai_mgr.get_providers()
            return ApiResponse.success(providers)
        except Exception as e:
            return ApiResponse.error(f"获取厂商列表失败: {str(e)}")

    @log_api_call
    def ai_get_models(self, temp_config: dict):
        """
        获取模型列表
        自带缓存机制，极速响应。
        :param temp_config: 前端表单中的临时配置 {provider, base_url, api_key}
        """
        try:
            models = self.ai_mgr.get_models(temp_config)
            return ApiResponse.success(models)
        except Exception as e:
            return ApiResponse.error(f"获取模型列表失败: {str(e)}")

    @log_api_call
    def ai_get_model_capabilities(self, temp_config: dict):
        """获取当前临时 AI 配置对应的模型能力摘要。"""
        try:
            capabilities = self.ai_mgr.get_model_capabilities(temp_config or {})
            return ApiResponse.success(capabilities)
        except Exception as e:
            return ApiResponse.error(f"获取模型能力失败: {str(e)}")

    @log_api_call
    def ai_chat(self, message: str, config_data: dict={}):
        """测试对话"""
        result = self._ai_check_enable_with_config(config_data)
        if not result['status'] == 'success': return result
        try:
            result = self.ai_mgr.test_chat(message, config_data)
            return ApiResponse.success(result)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def cancel_ai_session(self, session_id: str):
        """取消 AI 助手会话"""
        ok = self.ai_mgr.cancel_assistant_request(session_id)
        return ApiResponse.success() if ok else ApiResponse.error("取消失败，可能请求已完成或不存在")

    def _resolve_assistant_log_request(self, assistant_context: dict, request_payload: dict) -> tuple[str, str]:
        """解析助手会话中的日志来源信息。

        运行时唯一可信来源应当是 assistant_context.request_payload；
        如果调用方只给了 diagnosis_context 附件，则从附件 source 中兜底提取。
        """

        source_type = str(
            request_payload.get("source_type")
            or request_payload.get("log_source_type")
            or ""
        ).strip()
        filename = str(request_payload.get("filename") or "").strip()

        attachments = request_payload.get("attachments", []) or []
        if isinstance(attachments, list):
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                if str(attachment.get("kind") or "").strip() != "diagnosis_context":
                    continue
                source = dict(attachment.get("source") or {})
                source_type = source_type or str(source.get("source_type") or "").strip()
                filename = filename or str(source.get("filename") or "").strip()
                if source_type and filename:
                    break

        return source_type, filename

    def _normalize_assistant_session_payload(self, payload: dict) -> dict:
        """把前端 canonical assistant 请求整理成后端统一执行载荷。"""

        normalized_payload = dict(payload or {})
        assistant_context = dict(normalized_payload.get("assistant_context") or {})
        if not assistant_context:
            raise ValueError("assistant_context is required")

        request_payload = dict(assistant_context.get("request_payload") or {})
        question = str(
            assistant_context.get("question")
            or request_payload.get("question")
            or normalized_payload.get("question")
            or ""
        ).strip()
        attachments = list(request_payload.get("attachments", []) or normalized_payload.get("attachments", []) or [])
        enabled_tools = list(request_payload.get("enabled_tools", []) or normalized_payload.get("enabled_tools", []) or [])
        override_config = dict(
            request_payload.get("ai_override_config")
            or assistant_context.get("override_config")
            or normalized_payload.get("ai_override_config")
            or {}
        )
        source_type, filename = self._resolve_assistant_log_request(assistant_context, request_payload)

        request_payload.update({
            "question": question,
            "attachments": attachments,
            "enabled_tools": enabled_tools,
            "ai_override_config": override_config,
        })
        if source_type:
            request_payload["source_type"] = source_type
            request_payload["log_source_type"] = source_type
        if filename:
            request_payload["filename"] = filename

        assistant_context.update({
            "question": question,
            "override_config": override_config,
            "request_payload": request_payload,
        })

        normalized_payload.update({
            "assistant_context": assistant_context,
            "question": question,
            "attachments": attachments,
            "enabled_tools": enabled_tools,
            "ai_override_config": override_config,
        })
        if source_type:
            normalized_payload["log_source_type"] = source_type
        if filename:
            normalized_payload["filename"] = filename
        return normalized_payload

    def _resolve_assistant_request_runtime(self, payload: dict) -> tuple[dict, dict, dict, str, str, Any]:
        """统一解析助手请求执行所需的运行时上下文。"""
        normalized_payload = self._normalize_assistant_session_payload(payload)
        assistant_context = dict(normalized_payload.get("assistant_context") or {})
        request_payload = dict(assistant_context.get("request_payload") or {})
        source_type, filename = self._resolve_assistant_log_request(assistant_context, request_payload)
        reader = None
        if source_type:
            if source_type == 'app' and not settings.config.debug_mode:
                raise ValueError("软件日志分析仅在 Debug 模式下可用。")
            reader = self.game_log_mgr if source_type == 'game' else app_log_reader
            if not reader:
                raise ValueError("日志读取器未初始化")
        return normalized_payload, assistant_context, request_payload, source_type, filename, reader
    
    @log_api_call
    def ai_start_task(self, task_key: str, payload: dict | None = None):
        """统一启动异步 AI 任务。"""
        result = self.ai_check_enable()
        if not result['status'] == 'success': return result
        payload = dict(payload or {})
        task_id = str(uuid.uuid4())
        task_definition = (self.ai_mgr.tasks or {}).get(task_key) if hasattr(self.ai_mgr, "tasks") else {}
        task_title = str((task_definition or {}).get("name") or "AI 任务").strip() or "AI 任务"

        def background_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(
                    self.ai_mgr.execute_task_async(task_key, payload, task_id)
                )
                EventBus.emit("ai-task-complete", {
                    'task_id': task_id,
                    'status': 'cancelled' if results.get('cancelled') else 'success', 
                    'data': results
                })
            except Exception as e:
                logger.error(f"Background AI task failed: {e}", exc_info=True)
                EventBus.emit_progress(
                    task_id,
                    "ai-task",
                    status="failed",
                    progress=0,
                    message=f"AI 任务异常: {e}",
                    metrics={
                        "task_id": task_id,
                        "task_key": task_key,
                        "title": task_title,
                        "error": str(e),
                    },
                )
                EventBus.emit("ai-task-complete", {
                    'task_id': task_id,
                    'status': 'error', 
                    'message': str(e)
                })
            finally:
                try:
                    pending_tasks = [
                        task for task in asyncio.all_tasks(loop)
                        if not task.done()
                    ]
                    for pending_task in pending_tasks:
                        pending_task.cancel()
                    if pending_tasks:
                        loop.run_until_complete(
                            asyncio.gather(*pending_tasks, return_exceptions=True)
                        )
                except Exception as cleanup_error:
                    logger.warning(
                        f"Background AI task pending cleanup failed: {cleanup_error}",
                        exc_info=True,
                    )
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception as cleanup_error:
                    logger.warning(
                        f"Background AI task asyncgen cleanup failed: {cleanup_error}",
                        exc_info=True,
                    )
                try:
                    loop.run_until_complete(loop.shutdown_default_executor())
                except Exception as cleanup_error:
                    logger.warning(
                        f"Background AI task executor cleanup failed: {cleanup_error}",
                        exc_info=True,
                    )
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass
                loop.close()

        EventBus.emit_progress(
            task_id,
            "ai-task",
            status="pending",
            progress=0,
            message="任务已加入后台队列",
            metrics={
                "task_id": task_id,
                "task_key": task_key,
                "title": task_title,
            },
        )
        threading.Thread(target=background_worker, daemon=True).start()
        return ApiResponse.success({
            "task_id": task_id,
            "task_type": "ai-task",
            "task_key": task_key,
            "accepted": True,
            "status": "pending",
        }, message="AI 任务已在后台启动")
    
    @log_api_call
    def ai_prepare_diagnosis(self, payload: dict):
        """
        诊断预检接口：接收行号，提取日志内容，压缩并计算 Token。
        """
        raw_lines = payload.get("raw_lines", [])
        filename = payload.get("filename", "")
        source_type = payload.get("log_source_type", "game")
        if not raw_lines or not filename:
            return ApiResponse.error("无效的分析请求：缺失日志行号或文件名。")
        reader = self.game_log_mgr if source_type == 'game' else app_log_reader
        if not reader: return ApiResponse.error("日志读取器未初始化")
        
        if source_type == 'game':
            filepath = self.game_log_mgr.resolve_log_file_path(filename) if self.game_log_mgr else ""
        else:
            filepath = os.path.join(DATA_DIR, 'logs', filename)
        full_logs = reader.get_raw_logs_by_lines(filepath, raw_lines)
        if not full_logs:
            return ApiResponse.error("无法读取指定的日志内容，文件可能已被清理。")
        token_limit = settings.config.ai.resolved_max_input_tokens()
        from backend.managers.mgr_game_logs import LogCondenser
        condensed_data = LogCondenser.condense_for_ai( full_logs, token_limit=token_limit, stack_preview_lines=2 )
        from litellm import token_counter
        text_to_estimate = json.dumps(condensed_data, ensure_ascii=False)
        estimated_tokens = token_counter(model=settings.config.ai.model, text=text_to_estimate)
        logger.debug(
            f"[AI预检] source={source_type} filename={filename} raw_line_count={len(raw_lines)} "
            f"log_blocks={len(full_logs)} toc_items={len(condensed_data.get('error_table_of_contents', [])) if isinstance(condensed_data, dict) else 0} "
            f"estimated_tokens={estimated_tokens}"
        )
        # 【核心修改】无论是否超限，都返回统一数据结构给前端
        return ApiResponse.success({
            "is_over_limit": estimated_tokens > token_limit,
            "estimated_tokens": estimated_tokens,
            "token_limit": token_limit,
            "condensed_data": condensed_data
        })


    @log_api_call
    def ai_execute_assistant_session(self, payload: dict):
        """处理前端的通用助手会话请求。"""
        result = self.ai_check_enable()
        if not result['status'] == 'success': return result
        try:
            normalized_payload, assistant_context, request_payload, source_type, filename, reader = self._resolve_assistant_request_runtime(payload)
            session_id = str(normalized_payload.get("session_id") or "").strip()
            assistant_id = str(assistant_context.get("assistant_id") or "").strip()

            logger.debug(
                f"[AI会话API] 收到请求 session_id={session_id} "
                f"assistant_id={assistant_id} "
                f"source_type={source_type or '<empty>'} "
                f"filename={filename or '<empty>'} "
                f"history={len(request_payload.get('history', []) or [])} "
                f"attachments={len(request_payload.get('attachments', []) or [])}"
            )
            
            result = self.ai_mgr.run_assistant_session(normalized_payload, self.active_context, reader=reader)
            logger.debug(
                f"[AI会话API] 请求完成 session_id={session_id} "
                f"analysis_chars={len(result.get('analysis', '')) if isinstance(result, dict) else 0} "
                f"total_tokens≈{result.get('token_usage', {}).get('estimated_total_tokens', 0) if isinstance(result, dict) else 0}"
            )
            return ApiResponse.success(result)
        except Exception as e:
            # 增加异常堆栈打印，方便调试
            logger.error(f"智能会话异常: {str(e)}", exc_info=True)
            return ApiResponse.error(f"智能会话异常: {str(e)}")

    @log_api_call
    def ai_estimate_assistant_session_request(self, payload: dict):
        """按真实助手请求结构预估本轮主对话输入消耗。"""
        result = self.ai_check_enable()
        if not result['status'] == 'success': return result
        try:
            normalized_payload, assistant_context, request_payload, source_type, filename, reader = self._resolve_assistant_request_runtime(payload)

            logger.debug(
                f"[AI会话预估] session_id={normalized_payload.get('session_id', '')} "
                f"assistant_id={assistant_context.get('assistant_id', '')} "
                f"source_type={source_type or '<empty>'} "
                f"filename={filename or '<empty>'}"
            )
            result = self.ai_mgr.estimate_assistant_session_request(
                normalized_payload,
                self.active_context,
                reader=reader,
            )
            return ApiResponse.success(result)
        except Exception as e:
            logger.error(f"助手请求预估异常: {str(e)}", exc_info=True)
            return ApiResponse.error(f"助手请求预估异常: {str(e)}")

    # 供“一键排错”使用的全局扫描接口
    @log_api_call
    def ai_scan_global_errors(self, payload: dict):
        """
        直接读取完整日志块并生成全局错误摘要。
        """
        result = self.ai_check_enable()
        if not result['status'] == 'success': return result
        filename = payload.get("filename", "")
        source_type = payload.get("log_source_type", "game")
        logger.debug(f"[AI全局扫描] 开始 source={source_type} filename={filename}")
        if not filename:
            return ApiResponse.error("缺少文件名")
        reader = self.game_log_mgr if source_type == 'game' else app_log_reader
        if not reader: return ApiResponse.error("日志读取器未初始化")
        import os
        from backend.settings import DATA_DIR
        if source_type == 'game':
            filepath = self.game_log_mgr.resolve_log_file_path(filename) if self.game_log_mgr else ""
        else:
            filepath = os.path.join(DATA_DIR, 'logs', filename)
        if not os.path.exists(filepath):
            return ApiResponse.error("找不到日志文件")
        if not hasattr(reader, "get_all_blocks"):
            return ApiResponse.error("当前日志读取器不支持全局扫描")
        # 直接复用读取器已经合并好的结构化日志块，保证和普通多选分析一致。
        try:
            raw_logs = reader.get_all_blocks(filepath, full_scan=True)
        except Exception as e:
            logger.error(f"[AI全局扫描] 读取完整日志块失败 filename={filename}: {e}", exc_info=True)
            return ApiResponse.error(f"读取日志失败: {e}")
        if not raw_logs:
            return ApiResponse.warning("当前日志文件中没有可分析的内容。")
        # 全局扫描默认额外保留 2 行堆栈预览，并使用更保守的预算比例，
        # 这样前端能更快看到结果，也能让后续 AI 调用留出足够余量。
        token_limit = settings.config.ai.resolved_max_input_tokens()
        diagnosis_context = LogCondenser.condense_for_ai( raw_logs, token_limit=token_limit, char_budget_ratio=0.65, stack_preview_lines=2)
        # 压缩完成后再计算实际 Token 占用，前端顶部记忆计数直接使用这个结果。
        text_to_estimate = json.dumps(diagnosis_context, ensure_ascii=False)
        from litellm import token_counter
        estimated_tokens = token_counter(model=settings.config.ai.model, text=text_to_estimate)
        stats = diagnosis_context.get('stats', {}) if isinstance(diagnosis_context, dict) else {}
        compression_notice = (
            diagnosis_context.get('compression_notice')
            if isinstance(diagnosis_context, dict)
            else ""
        )

        logger.debug(
            f"[AI全局扫描] 完成 source={source_type} filename={filename} "
            f"log_blocks={len(raw_logs)} error_blocks={stats.get('error_block_count', 0)} "
            f"grouped_items={stats.get('grouped_error_count', 0)} toc_items={stats.get('output_item_count', 0)} "
            f"estimated_tokens={estimated_tokens}"
        )

        return ApiResponse.success({
            "is_over_limit": estimated_tokens > token_limit,
            "estimated_tokens": estimated_tokens,
            "token_limit": token_limit,
            "condensed_data": diagnosis_context,
            "compression_notice": compression_notice
        })
    
    @log_api_call
    def ai_save_prompt(self, prompt_id: str, prompt_data: dict):
        """保存提示词"""
        try:
            res = self.ai_mgr.save_prompt(prompt_id, prompt_data)
            return ApiResponse.success(res)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_delete_prompt(self, prompt_id: str):
        """删除提示词"""
        try:
            res = self.ai_mgr.delete_prompt(prompt_id)
            return ApiResponse.success(res)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_save_assistant(self, assistant_id: str, assistant_data: dict):
        """保存助手定义"""
        try:
            res = self.ai_mgr.save_assistant(assistant_id, assistant_data)
            return ApiResponse.success(res)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_save_task(self, task_id: str, task_data: dict):
        """保存任务定义"""
        try:
            res = self.ai_mgr.save_task(task_id, task_data)
            return ApiResponse.success(res)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_get_trace_records(self, session_id: str = ""):
        """获取运行期 AI 请求链记录。

        当前返回的是“按会话归档”的链路数据：
        - 不传 `session_id` 时返回所有会话摘要
        - 传入后返回单个会话的完整链路
        """
        try:
            normalized_session_id = str(session_id or "").strip()
            return ApiResponse.success(self.ai_mgr.get_trace_records(normalized_session_id or None))
        except Exception as e:
            return ApiResponse.error(str(e))
    
    
    # ==========================================
    #  13. 用户配置环境管理 (Profiles)
    # ==========================================
    @log_api_call
    def profiles_get(self):
        '''获取所有环境配置'''
        return ApiResponse.success(self.profile_mgr.get_all_profiles())

    @log_api_call
    def profile_get_current(self):
        '''获取当前环境配置'''
        return ApiResponse.success(self.profile_mgr.get_current_profile())
    
    @log_api_call
    def profile_create(self, data: Dict[str, Any], copy_current_data: bool = False):
        try:
            self.profile_mgr.create_profile(data, copy_current_data)
            return ApiResponse.success(message="环境创建成功")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def profile_update(self, pid: str, data: Dict[str, Any]):
        try:
            self.profile_mgr.update_profile(pid, data)
            if pid == settings.config.current_profile_id:
                refresh_mode = self._refresh_active_profile_context_after_update(pid, data)
                active_profile_id = str(getattr(getattr(self, 'active_context', None), 'profile_id', '') or '').strip()
                if active_profile_id:
                    self._sync_runtime_links_for_profile(active_profile_id, include_workshop=True)
                return ApiResponse.success(
                    message="配置已更新",
                    data={"refresh_mode": refresh_mode},
                )
            return ApiResponse.success(message="配置已更新")
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def profile_delete(self, pid, force: bool = False):
        try:
            self.profile_mgr.delete_profile(pid, force=force)
            return ApiResponse.success(message="环境已删除")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def profile_activate(self, pid):
        """
        切换环境。
        前端调用此方法后，应该紧接着调用 get_initial_data 刷新界面。
        """
        try:
            self._bootstrap_context(pid)
            active_profile_id = str(getattr(getattr(self, 'active_context', None), 'profile_id', '') or '').strip()
            if active_profile_id:
                self._sync_runtime_links_for_profile(active_profile_id, include_workshop=True)
            # 切换成功后，前端通常会调用 get_initial_data 刷新全界面，所以这里只需返回成功
            res = {
                "profile": self.profile_mgr.get_current_profile().__dict__,
                "context": self.active_context.__dict__,
                "settings": asdict(settings.config)
            }
            return ApiResponse.success(message=f"已切换到环境: {pid}", data=res)
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def profiles_scan_orphaned(self):
        """扫描可恢复的配置"""
        orphans = self.profile_mgr.scan_orphaned_profiles()
        return ApiResponse.success(orphans)

    @log_api_call
    def profile_import_orphaned(self, profile_data):
        """导入选定的配置"""
        success, msg = self.profile_mgr.import_profile_from_disk(profile_data)
        if success:
            return ApiResponse.success(message=msg)
        else:
            return ApiResponse.error(msg)

    def _reload_community_rules(self):
        """外部规则文件更新后，立即把内存中的规则缓存切到新版本。"""
        if not self.sorter or not self.sorter.rule_mgr:
            EventBus.send_toast("规则引擎未初始化，无法立即重载社区规则库。", type="warning")
            return
        logger.info("Community rules ready, reloading...")
        self.sorter.rule_mgr.load_all()

    def _reload_workshop_database(self):
        """工坊数据库更新后，同时刷新依赖规则缓存，避免前端继续读旧关联关系。"""
        logger.info("Workshop database ready, reloading...")
        self.workshop_db_mgr.load_all_cache()
        if self.sorter and self.sorter.rule_mgr:
            self.sorter.rule_mgr.build_workshop_rules()

    def _reload_instead_database(self):
        """替代库更新后只需重建外置缓存。"""
        logger.info("Instead database ready, reloading...")
        self.workshop_db_mgr.rebuild_instead_cache()
    
    
    # ==========================================
    #  14. 外置数据管理 (External Data)
    # ==========================================
    @log_api_call
    def update_external_db(self, data_type: str):
        """
        更新外置数据。

        这里统一承接三类外部库文件：
        1. 社区规则库
        2. 社区工坊数据库
        3. 替代 Mod 数据库
        """
        try:
            dataset_specs = {
                "community_rules": {
                    "path": settings.config.community_rules_path,
                    "url": settings.config.community_rules_url,
                    "success_message": "社区规则库更新完毕！",
                    "error_message": "社区规则库更新失败！",
                    "start_message": "社区规则库开始更新",
                    "reload": self._reload_community_rules,
                },
                "workshop_db": {
                    "path": settings.config.community_workshop_db_path,
                    "url": settings.config.community_workshop_db_url,
                    "success_message": "社区工坊数据库更新完毕！",
                    "error_message": "社区工坊数据库更新失败！",
                    "start_message": "社区工坊数据库开始更新",
                    "reload": self._reload_workshop_database,
                },
                "instead_db": {
                    "path": settings.config.community_instead_db_path,
                    "url": settings.config.community_instead_db_url,
                    "success_message": "替代 Mod 数据库更新完毕！",
                    "error_message": "替代 Mod 数据库更新失败！",
                    "start_message": "替代 Mod 数据库开始更新",
                    "reload": self._reload_instead_database,
                },
            }
            spec = dataset_specs.get(data_type)
            if not spec:
                return ApiResponse.error(f"无效的数据库类型 {data_type}")

            full_path = str(spec["path"] or "")
            url = str(spec["url"] or "")
            if not full_path or not url:
                return ApiResponse.error("更新地址或目标路径未配置")

            file_folder = os.path.dirname(full_path)
            file_name = os.path.basename(full_path)
            if not os.path.exists(file_folder):
                os.makedirs(file_folder, exist_ok=True)

            logger.info("Start updating external dataset %s from: %s", data_type, url)

            def on_db_ready(task):
                try:
                    reload_fn = spec.get("reload")
                    if callable(reload_fn):
                        reload_fn()
                    EventBus.send_toast(str(spec["success_message"]), type="success")
                except Exception as reload_error:
                    logger.error("External dataset reload failed: %s", reload_error, exc_info=True)
                    EventBus.send_toast(f"{spec['success_message']} 但重载失败，请稍后手动刷新。", type="warning")

            def on_db_error(task):
                logger.error("%s download failed: %s", data_type, getattr(task, "error_msg", ""), exc_info=True)
                EventBus.send_toast(str(spec["error_message"]), type="error")

            task_id = self.download_mgr.add_task(
                url=url,
                dest_dir=file_folder,
                filename=file_name,
                on_complete=on_db_ready,
                on_error=on_db_error
            )

            return ApiResponse.success(data={"task_id": task_id}, message=str(spec["start_message"]))
        except Exception as e:
            logger.error(f"Update community {data_type} failed: {e}", exc_info=True)
            return ApiResponse.error(f"系统错误: {str(e)}")
    
    @log_api_call
    def lifecycle_check_updates(self):
        """
        生命周期核心：同时检查 workshop 域与 self 域的已安装模组更新状态。

        - workshop 域：优先使用 Steamworks 试验适配层读取 Steam 客户端本机状态；
        - self 域：继续使用 Steam Web API 在线时间与本地安装时间做比对。
        """
        workshop_local_data = self.steam_mgr.workshop_merged_data()
        manager_local_data = self.steam_mgr.steamcmd_merged_data()

        workshop_installed_wids = {
            str(item.get("workshop_id") or "").strip()
            for item in workshop_local_data.values()
            if item.get("is_installed") and str(item.get("workshop_id") or "").strip().isdigit()
        }
        self_installed_wids = {
            str(item.get("workshop_id") or "").strip()
            for item in manager_local_data.values()
            if item.get("is_installed") and str(item.get("workshop_id") or "").strip().isdigit()
        }

        logger.debug(
            "生命周期更新检查：workshop 合并数据 %s 条，已安装 %s 条；self 合并数据 %s 条，已安装 %s 条",
            len(workshop_local_data),
            len(workshop_installed_wids),
            len(manager_local_data),
            len(self_installed_wids),
        )

        updates_available = []

        if workshop_installed_wids:
            steam_running = bool(self.steam_mgr.is_steam_running())
            if not steam_running:
                logger.debug(
                    "生命周期更新检查[workshop]：Steam 未运行，跳过 Steamworks 检查（待检 %s 条）",
                    len(workshop_installed_wids),
                )
            else:
                workshop_state_result = self.steam_mgr.query_workshop_item_states(
                    list(workshop_installed_wids),
                    timeout_seconds=12.0,
                )
                workshop_states = workshop_state_result.get("states") if isinstance(workshop_state_result, dict) else {}
                workshop_states = workshop_states if isinstance(workshop_states, dict) else {}
                logger.debug(
                    "生命周期更新检查[workshop]：Steamworks 可用 %s，ready %s，检查 %s 条，命中状态 %s 条，detail=%s",
                    bool(workshop_state_result.get("available")) if isinstance(workshop_state_result, dict) else False,
                    bool(workshop_state_result.get("ready")) if isinstance(workshop_state_result, dict) else False,
                    len(workshop_installed_wids),
                    len(workshop_states),
                    str((workshop_state_result or {}).get("detail") or ""),
                )
                for local_item in workshop_local_data.values():
                    if not local_item.get("is_installed"):
                        continue
                    wid = str(local_item.get("workshop_id") or "").strip()
                    state_info = workshop_states.get(wid) or {}
                    if not state_info or not state_info.get("needs_update"):
                        continue
                    updates_available.append({
                        "workshop_id": wid,
                        "title": wid,
                        "source": "workshop",
                        "local_time": int(local_item.get("time_downloaded") or local_item.get("installed_version_time") or 0),
                        "online_time": int(local_item.get("latest_version_time") or 0),
                        "preview_url": "",
                    })

        if self_installed_wids:
            online_details, _ = SteamWebAPI.fetch_item_details(
                list(self_installed_wids),
                trace_label="lifecycle_check_updates:self",
            )
            for local_item in manager_local_data.values():
                if not local_item.get('is_installed'):
                    continue
                wid = str(local_item.get('workshop_id') or '').strip()
                online_info = online_details.get(wid)
                if not online_info:
                    continue
                local_time = int(local_item.get('time_downloaded') or local_item.get('installed_version_time') or 0)
                online_time = int(online_info.get('time_updated') or 0)
                if online_time <= local_time + 3600 * 1000:
                    continue
                updates_available.append({
                    "workshop_id": wid,
                    "title": online_info.get("title") or wid,
                    "source": "self",
                    "local_time": local_time,
                    "online_time": online_time,
                    "preview_url": online_info.get("preview_url") or "",
                })
        else:
            logger.debug("生命周期更新检查[self]：没有可检查的已安装 self 模组")

        return ApiResponse.success({"updates": updates_available})

    @log_api_call
    def get_replacement_suggestion(self, package_id: str):
        """
        获取 Mod 替换建议：根据当前启用的 Mod，查询是否有更好的替代版本
        """
        # 1. 从数据库查询当前启用的 Mod 信息
        game_version = self.active_context.game_version if self.active_context else ''
        ext_mod = ExtDAO.get_replacement_suggestion(package_id, game_version)
        if not ext_mod: return ApiResponse.warning(f"Mod {package_id} 没有替换建议")
        return ApiResponse.success({"replacement": ext_mod})
        
    @log_api_call
    def lifecycle_resolve_dependencies(self, active_package_ids: list):
        """
        一键检测前置依赖：扫描当前启用的包，找出缺失的依赖，并直接转换为可下载的工坊 ID
        """
        # 1. 搜集当前启用的所有 Mod 数据
        installed_mods = ModDAO.get_profile_mods(self.active_context)
        installed_pids = set([m['package_id'].lower() for m in installed_mods])
        missing_dependencies = {} # { "workshop_id": "name" }
        # 2. 遍历启用的 Mod，提取依赖要求
        for pid in active_package_ids:
            pid = pid.lower()
            mod_data = next((m for m in installed_mods if m['package_id'].lower() == pid), None)
            # 来源 A: 本地 About.xml 解析出的 rules
            if mod_data and 'rules' in mod_data:
                for dep in mod_data['rules'].get('dependencies', []):
                    target_pid = dep['target_id'].lower()
                    if target_pid not in installed_pids:
                        # 缺失！通过外置数据库反查工坊 ID
                        wid = ExtDAO.get_workshop_id_by_package(target_pid)
                        if wid:
                            missing_dependencies[wid] = target_pid # 暂存
            # 来源 B: 直接查询外置数据库 (Ext_DB) 中的依赖
            # (即使本地没写，社区库可能记录了隐藏依赖)
            self_wid = ExtDAO.get_workshop_id_by_package(pid)
            if self_wid:
                # 调用 ext_db 的模型查询该 Mod 的全量云端依赖
                meta = ExtDAO.get_manifest_by_workshop_id(self_wid)
                if meta and meta.dependencies_mods:
                    dep_manifest_map = ExtDAO.get_manifests_by_workshop_ids(list(meta.dependencies_mods.keys()))
                    for dep_wid, dep_name in meta.dependencies_mods.items():
                        # 反查依赖项的包名看本地有没有装
                        dep_meta = dep_manifest_map.get(str(dep_wid))
                        dep_pid = dep_meta.package_id if dep_meta else None
                        if dep_pid and dep_pid not in installed_pids:
                            missing_dependencies[dep_wid] = dep_name
        if not missing_dependencies:
            return ApiResponse.success({"missing": []}, message="前置依赖完整，无需补充。")
        # 3. 补充线上详情供 UI 渲染 (名称、封面)
        details, ids_to_fetch = SteamWebAPI.fetch_item_details(list(missing_dependencies.keys()))
        result = []
        for wid, fallback_name in missing_dependencies.items():
            info = details.get(wid, {})
            result.append({
                "workshop_id": wid,
                "name": info.get("title", fallback_name),
                "preview_url": info.get("preview_url", "")
            })
        return ApiResponse.success({"missing": result})
    
    @log_api_call
    def get_mod_workshop_detail(self, workshop_id: str, force_refresh: bool = False):
        """
        获取单个 Mod 的完整工坊详情（含截图、长介绍、在线状态）
        """
        if not workshop_id: return ApiResponse.error("无效的工坊 ID")
        # 1. 调度：从缓存或网络获取
        details, ids_to_fetch = SteamWebAPI.fetch_item_details([workshop_id], force_refresh=force_refresh)
        info = details.get(str(workshop_id))
        if not info: return ApiResponse.error("无法从 Steam 获取该模组详情")
        
        # 将原始截图 URL 转换为代理缓存 URL
        cache_screenshots = []
        for raw_url in info.get("screenshots", []):
            cache_url = file_mgr.get_gallery_url(workshop_id, raw_url)
            cache_screenshots.append(cache_url)
        
        # 需要先查出这个工坊 ID 对应的 PackageID, 才能查询替代建议
        meta = ExtDAO.get_merged_meta_by_workshop_id(str(workshop_id))
        replacement = None
        game_version = self.active_context.game_version if self.active_context else ''
        if meta and meta.get("package_id"):
            replacement = self.workshop_db_mgr.check_replacement(str(meta.get("package_id")), game_version)
        # 3. 组合最终对象
        return ApiResponse.success({
            "workshop_id": workshop_id,
            "title": info["title"],
            "description": info["description"],
            "screenshots": cache_screenshots, # 这里的 URL 列表直接发给前端 v-for
            "preview_url": info["preview_url"],
            "online_time": info["time_updated"],
            "replacement": replacement # 如果有替代品，这里会包含 new_id 和 new_name
        })
    
    @log_api_call
    def get_workshop_ids_by_package_ids_map(self, package_ids: list[str]):
        """
        根据 PackageID 获取对应的 WorkshopID 映射
        """
        if not package_ids: return ApiResponse.error("无效的 PackageID")
        current_game_version = self.active_context.game_version if self.active_context else ""
        details = ExtDAO.get_workshop_details_by_package_ids(package_ids, current_game_version=current_game_version)
        if not details:
            return ApiResponse.error("未找到对应的 WorkshopID")
        return ApiResponse.success({
            package_id: (((detail or {}).get("display") or {}).get("selected") or {}).get("workshop_id")
            for package_id, detail in details.items()
            if (((detail or {}).get("display") or {}).get("selected") or {}).get("workshop_id")
        })
    
    @log_api_call
    def get_workshop_details_by_package_ids(self, package_ids: list):
        """
        批量获取包名对应的缓存信息（完全离线，无网络请求）
        """
        try:
            current_game_version = self.active_context.game_version if self.active_context else ""
            res = ExtDAO.get_workshop_details_by_package_ids(package_ids, current_game_version=current_game_version)
            return ApiResponse.success(res)
        except Exception as e:
            logger.error(f"get_workshop_details_by_package_ids failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))

    @log_api_call
    def get_install_sources_by_package_ids(self, package_ids: list):
        """
        批量获取 package_id 的原版安装来源与替代安装来源。
        """
        try:
            current_game_version = self.active_context.game_version if self.active_context else ""
            res = ExtDAO.get_install_sources_by_package_ids(package_ids, current_game_version=current_game_version)
            return ApiResponse.success(res)
        except Exception as e:
            logger.error(f"get_install_sources_by_package_ids failed: {e}", exc_info=True)
            return ApiResponse.error(str(e))
    
    @log_api_call
    def workspace_get_all_domains(self):
        """
        三域数据全量获取 (统合 DB、ACF、Log 数据)
        """
        # 1. 获取数据库基础数据 (含有 URL)
        matrix = ModDAO.get_triple_domain_assets(self.active_context)
        # 2. 获取 Steam 状态数据 (ACF/Log)
        ws_map = self.steam_mgr.workshop_merged_data()
        mg_map = self.steam_mgr.steamcmd_merged_data()
        replacements_map = {
            str(r['old_workshop_id']): r
            for r in self.workshop_db_mgr.get_replacements()
            if r.get('old_workshop_id')
        }
        
        install_workshop_ids = set()
        # install_self_ids = set()
        
        def inject_workspace_fields(mod: dict, steam_map: dict | None = None):
            wid = str(mod.get('workshop_id') or '')
            if steam_map and wid and wid in steam_map:
                mod['steam_status'] = steam_map[wid]
            mod['replacement'] = replacements_map.get(wid)
            mod['is_missing'] = False
            return wid

        # 3. 为已有的物理模组注入 Steam 状态
        for mod in matrix['workshop']:
            wid = inject_workspace_fields(mod, ws_map)
            if mod.get('path') and wid:
                install_workshop_ids.add(wid)
        
        # 为 self (管理器) 域注入数据
        for mod in matrix['self']:
            inject_workspace_fields(mod, mg_map)
            # if mod.get('path'): install_self_ids.add(wid)
        
        for mod in matrix['local']:
            inject_workspace_fields(mod)
        
        # 4. 核心逻辑：找出“已订阅但物理丢失”的模组 (Ghost Mods)
        # 找出 ACF 中标记已订阅，但物理文件没被扫描到的 ID
        ghost_ws_ids = set([wid for wid, data in ws_map.items() if data.get('is_subscribed')]) - install_workshop_ids
        # ghost_self_ids = set([wid for wid, data in mg_map.items() if data.get('is_subscribed')]) - install_self_ids
        
        # 5. 从 ExtDB (外置社区库) 中获取这些幽灵模组的信息，使其在 UI 上能显示名字和图片
        all_ghost_ids = list(ghost_ws_ids)
        ghost_meta_map = {}
        if all_ghost_ids:
            ghost_meta_map = ExtDAO.get_workshop_details_by_workshop_ids(all_ghost_ids)

        # 构造幽灵模组对象并塞回对应列表
        def create_ghost(wid, store_type, steam_status):
            meta = ghost_meta_map.get(wid, {})
            return {
                "workshop_id": wid,
                "package_id": f"ghost.{wid}", # 临时包名防止前端 key 报错
                "name": meta.get('name') or f"未知/已下架模组 ({wid})",
                "preview_url": meta.get('preview_url'),
                "path": "", # 路径为空
                "path_hash": f"ghost_{store_type}_{wid}", # 临时唯一哈希
                "store": store_type,
                "source": "workshop",
                "is_missing": True, 
                "steam_status": steam_status,
                "replacement": replacements_map.get(wid)
            }
        for wid in ghost_ws_ids:
            matrix['workshop'].append(create_ghost(wid, 'workshop', ws_map.get(wid)))
            
        res = {
            "workshop": matrix['workshop'],
            "self": matrix['self'],
            "local": matrix['local']
        }
        
        # 6. 后台触发在线比对，统一只针对 self / SteamCMD 域做在线状态预热与更新标记。
        all_wids = list({
            str(item.get("workshop_id") or "").strip()
            for item in mg_map.values()
            if item.get("is_installed") and str(item.get("workshop_id") or "").strip().isdigit()
        })
        logger.debug(
            "工作区在线预热[self]：workshop 总数 %s / 已安装 %s，steamcmd 总数 %s / 已安装 %s，实际预热 %s",
            len(ws_map),
            sum(1 for item in ws_map.values() if item.get("is_installed")),
            len(mg_map),
            sum(1 for item in mg_map.values() if item.get("is_installed")),
            len(all_wids),
        )
        if all_wids:
            import threading
            threading.Thread(target=self._bg_check_online_updates, args=(all_wids,), daemon=True).start()

        return ApiResponse.success(res)
    
    def _bg_check_online_updates(self, all_wids: list):
        """后台静默检测，完成后通过 EventBus 推送"""
        online_info, ids_to_fetch = SteamWebAPI.fetch_item_details(
            all_wids,
            only_cache=True,
            trace_label="workspace_preheat:self",
        )
        logger.debug(
            "工作区在线预热[self]：缓存预热完成，命中 %s 条，待联网 %s 条（本阶段不发起在线请求）",
            len(online_info),
            len(ids_to_fetch),
        )
        # 把算好的 online_info 推给前端，前端进行响应式合并
        from backend.utils.event_bus import EventBus
        EventBus.emit('workspace-online-update', online_info)
        
        # matrix['need_refresh'] = ids_to_fetch
        # def mark_update(mod_list):
        #     for mod in mod_list:
        #         wid = str(mod.get('workshop_id'))
        #         if wid in online_info and 'steam_status' in mod:
        #             local_time = mod['steam_status'].get('time_downloaded') or \
        #                         mod['steam_status'].get('installed_version_time') or 0
        #             online_time = online_info[wid].get('time_updated', 0)
        #             # 注入更新标记, 云端更新时间大于本地下载时间 + 1h 则认为有更新
        #             mod['has_update'] = online_time > (local_time + 3600 * 1000)
        #             mod['online_info'] = online_info[wid] # 顺便存一份云端简介和标题
        # mark_update(matrix['workshop'])
        # mark_update(matrix['self'])
        # return ApiResponse.success(matrix)
    
    @log_api_call
    def workspace_trigger_online_refresh(self, workshop_ids: list):
        """
        第二阶段：异步网络请求，通过 EventBus 分批推送最新状态
        """
        normalized_ids = []
        seen_ids = set()
        for workshop_id in workshop_ids or []:
            normalized_id = str(workshop_id or "").strip()
            if not normalized_id or not normalized_id.isdigit() or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            normalized_ids.append(normalized_id)

        logger.debug("工作区强制在线刷新：收到 %s 个请求 ID，规范化后 %s 个", len(workshop_ids or []), len(normalized_ids))
        if not normalized_ids:
            return ApiResponse.success(message="没有可刷新的工坊项目")

        def worker():
            from backend.managers.mgr_steam_api import SteamWebAPI
            from backend.utils.event_bus import EventBus
            
            # 100 个一组分批请求，防止 URL 过长或单次请求过久
            for i in range(0, len(normalized_ids), 100):
                batch = normalized_ids[i:i+100]
                # 这里调用真实的联网请求
                online_data, _ = SteamWebAPI.fetch_item_details(
                    batch,
                    force_refresh=True,
                    trace_label="workspace_force_refresh:self",
                )
                
                # 每完成一批，立即推送
                EventBus.emit('workspace-online-update', online_data)
                
        import threading
        threading.Thread(target=worker, daemon=True).start()
        return ApiResponse.success(message="后台更新检查已启动")
    
    @log_api_call
    def workspace_get_mod_timeline(self, workshop_id: str, is_steamcmd: bool = False):
        """获取 Mod 变动轨迹"""
        return ApiResponse.success(self.steam_mgr.get_item_timeline(workshop_id, is_steamcmd))
    
    @log_api_call
    def workshop_search(self, query: str, page: int = 1):
        """离线库搜索 + 在线静默预热"""
        # 1. 从本地 SQLite 获取当前页的数据 (瞬间完成)
        data = ExtDAO.search_workshop(query, page, page_size=100)
        items = data['items']
        if items:
            # 2. 提取 ID 列表，去 Steam 检查是否有更新 (利用你已有的缓存机制)
            workshop_ids = [item['workshop_id'] for item in items]
            # 只取缓存或触发网络请求更新 DB。因为你设置了 1天的 TTL，大部分情况下也是瞬间返回
            online_info, _ = SteamWebAPI.fetch_item_details(workshop_ids, force_refresh=False)
            
            # 3. 将最新的封面和名字合并回 items
            for item in items:
                wid = item['workshop_id']
                if wid in online_info:
                    item['preview_url'] = online_info[wid].get('preview_url', item['preview_url'])
                    item['name'] = online_info[wid].get('title', item['name'])
                    item['time_updated'] = online_info[wid].get('time_updated', item.get('time_updated'))

        return ApiResponse.success(data)

    @log_api_call
    def workshop_search_online(self, query: str, cursor: str = "*", page_size: int = 25, sort: str = "relevance"):
        """使用 Steam Web API 在线搜索工坊条目。"""
        try:
            data = SteamWebAPI.search_workshop_online(query, cursor=cursor, page_size=page_size, sort=sort)
            return ApiResponse.success(data)
        except ValueError as exc:
            return ApiResponse.warning(str(exc))
        except Exception as exc:
            return ApiResponse.error(f"在线工坊搜索失败: {exc}")

    @log_api_call
    def workshop_get_details(self, workshop_id: str):
        """获取云端详细图文"""
        details = SteamWebAPI.get_or_fetch_details(workshop_id)
        if details:
            return ApiResponse.success(details)
        return ApiResponse.error("未找到模组详情")

    
    # ==========================================
    # 收藏合集相关接口
    # ==========================================
    @log_api_call
    def collection_get_all(self):
        """从数据库获取已保存的合集列表"""
        return ApiResponse.success(CollectionDAO.get_all())

    @log_api_call
    def collection_remove(self, collection_id: str):
        """从数据库移除合集"""
        CollectionDAO.delete(collection_id)
        return ApiResponse.success(message="合集已移出名录")
    
    @log_api_call
    def collection_add(self, collection_id: str):
        """
        同步解析并接入新合集。
        阻塞请求直到爬取完成，确保前端能立即得到数据。
        """
        coll_id = str(collection_id)
        child_wids = SteamWebAPI.fetch_collection_children(coll_id)
        if not child_wids: return ApiResponse.error("无效的合集或合集为空")

        all_ids = list(set([coll_id] + child_wids))
        online_results, _ = SteamWebAPI.fetch_item_details(all_ids, force_refresh=True)
        if coll_id not in online_results: return ApiResponse.error("无法获取合集信息")
        main_info = online_results[coll_id]
        final_children = self._build_collection_children(child_wids, online_results)

        total = len(final_children)
        # 持久化
        CollectionDAO.upsert_collection(coll_id, main_info, final_children, total)
        # 重新取回完整结构返回给前端
        new_coll = CollectionDAO.get_collection_by_id(coll_id)
        return ApiResponse.success(model_to_dict(new_coll))

    @log_api_call
    def lifecycle_fetch_collection(self, collection_id: str):
        """
        合集加载引擎 (分步模式，24小时缓存)：
        1. 立即从数据库返回缓存数据 (包含上一次的子项快照)
        2. 启动后台线程，执行：网络解析 -> 状态对比 -> 存库 -> EventBus 通知刷新
        """
        coll_id = str(collection_id)
        cached_coll = CollectionDAO.get_collection_by_id(coll_id) # 获取缓存
        is_fresh = False
        initial_data = None
        if cached_coll:
            # 检查缓存是否在 24 小时内
            if current_ms() - cached_coll.last_sync_time < 24 * 3600 * 1000: is_fresh = True
            initial_data = {
                "collection": model_to_dict(cached_coll),
                "children": cached_coll.children or [],
                "total": cached_coll.total,
                "is_cache": True # 标记这是缓存
            }
        # 如果没有缓存，或者缓存已过期，启动后台刷新
        if not is_fresh:
            self._start_tracked_main_db_task("collection-refresh", self._bg_refresh_collection, coll_id)

        return ApiResponse.success(initial_data)

    def _resolve_collection_package_map(self, child_wids: list[str]) -> dict[str, str]:
        normalized_wids: list[str] = []
        seen_wids: set[str] = set()
        for wid in child_wids:
            wid_str = str(wid or '').strip()
            if wid_str and wid_str not in seen_wids:
                seen_wids.add(wid_str)
                normalized_wids.append(wid_str)

        if not normalized_wids: return {}

        resolved_map: dict[str, str] = {}
        manifest_map = ExtDAO.get_manifests_by_workshop_ids(normalized_wids)
        for wid, manifest in manifest_map.items():
            pid = manifest.package_id
            if wid and pid:
                resolved_map[wid] = pid

        store_priority = {'workshop': 0, 'self': 1, 'local': 2}
        installed_candidates: dict[str, dict[str, dict[str, int]]] = {}
        asset_records = (
            ModAsset
            .select(
                ModAsset.workshop_id,
                ModAsset.package_id,
                ModAsset.store,
                ModAsset.disabled,
                ModAsset.path
            )
            .where(ModAsset.workshop_id.in_(normalized_wids)) # type: ignore
            .dicts()
        )
        for asset in asset_records:
            wid = str(asset.get('workshop_id') or '').strip()
            pid = asset.get('package_id')
            if not wid or not pid:
                continue

            candidates_by_pid = installed_candidates.setdefault(wid, {})
            candidate = candidates_by_pid.setdefault(pid, {
                'count': 0,
                'disabled_rank': 1,
                'store_rank': 99,
                'path_len': 10 ** 9,
            })
            candidate['count'] += 1
            candidate['disabled_rank'] = min(candidate['disabled_rank'], 1 if asset.get('disabled') else 0)
            candidate['store_rank'] = min(candidate['store_rank'], store_priority.get(asset.get('store'), 99))
            path_len = len(str(asset.get('path') or '').strip())
            if path_len > 0:
                candidate['path_len'] = min(candidate['path_len'], path_len)

        for wid, candidates in installed_candidates.items():
            best_pid = min(
                candidates.items(),
                key=lambda item: ( -item[1]['count'], item[1]['disabled_rank'], item[1]['store_rank'], item[1]['path_len'], item[0] )
            )[0]
            resolved_map[wid] = best_pid

        return resolved_map

    def _build_collection_children(self, child_wids: list[str], online_results: dict[str, dict]) -> list[dict]:
        pid_map = self._resolve_collection_package_map(child_wids)
        final_children: list[dict] = []
        seen_wids: set[str] = set()

        for raw_wid in child_wids:
            wid = str(raw_wid or '').strip()
            if not wid or wid in seen_wids:
                continue
            seen_wids.add(wid)

            info = online_results.get(wid, {})
            final_children.append({
                "workshop_id": wid,
                "package_id": pid_map.get(wid),
                "title": info.get("title", f"Mod {wid}"),
                "preview_url": info.get("preview_url", "")
            })

        return final_children

    def _bg_refresh_collection(self, coll_id: str):
        """后台刷新任务 (网络密集 + 数据库写入)"""
        try:
            logger.debug(f"开始后台刷新合集: {coll_id}")
            # 1. 抓取最新子项 ID 列表
            child_wids = SteamWebAPI.fetch_collection_children(coll_id)
            # 2. 抓取所有项（含合集本身）的最新详情，这里的 batch_ids 包含合集 ID 自己
            all_ids = list(set([coll_id] + child_wids))
            online_results, _ = SteamWebAPI.fetch_item_details(all_ids, force_refresh=True)
            
            if coll_id not in online_results: return
            main_info = online_results[coll_id]

            # 3. 组装并准备持久化
            final_children = self._build_collection_children(child_wids, online_results)
            total = len(final_children)
            # 6. 存入数据库
            CollectionDAO.upsert_collection(coll_id, main_info, final_children, total)

            # 7. 通过 EventBus 通知前端：数据已就绪，请刷新
            EventBus.emit('workspace-collection-updated', {
                "id": coll_id,
                "data": {
                    "collection": main_info,
                    "children": final_children,
                    "total": total,
                    "is_cache": False
                }
            })
            logger.debug(f"后台刷新合集完成: {coll_id}")

        except Exception as e:
            logger.error(f"后台刷新合集失败: {e}", exc_info=True)
    
    
    # ==========================================
    # GitHub 相关接口
    # ==========================================
    @log_api_call
    def github_fetch_info(self, url: str, source_branch: str = ""):
        """解析并获取远程仓库信息"""
        res = self.github_mgr.fetch_repo_info(url, source_branch=source_branch)
        if "error" in res: return ApiResponse.error(res["error"])
        return ApiResponse.success(res)

    @log_api_call
    def github_subscribe(self, payload: dict):
        """添加订阅到数据库"""
        url = payload.get("url")
        if not url: return ApiResponse.error("URL 不能为空")
        installed_version = str(payload.get("installed_version") or "").strip()
        info = payload.get("info") or {}
        install_type = str(payload.get("install_type") or "source").strip() or "source"
        target_branch = str(payload.get("default_branch") or "").strip() or "main"

        with db.atomic():
            record, created = GithubModRecord.get_or_create(
                repo_url=url,
                defaults={
                    "owner": payload.get("owner"),
                    "repo_name": payload.get("repo"),
                    "target_branch": target_branch,
                    "install_type": install_type,
                    "installed_version": installed_version,
                    "online_info_cache": info,
                    "last_sync_time": current_ms(),
                }
            )
            if created:
                self.github_mgr.record_timeline(url, "subscribe", "已添加 GitHub 仓库监听记录")
            else:
                # 再次订阅同一仓库时，更新监听策略和最新在线缓存，但不擅自覆盖已部署版本。
                record.owner = payload.get("owner") or record.owner
                record.repo_name = payload.get("repo") or record.repo_name
                record.target_branch = target_branch
                record.install_type = install_type
                record.online_info_cache = info
                record.last_sync_time = current_ms()
                if installed_version:
                    record.installed_version = installed_version
                record.save()
        return self.github_get_subscribed() # 返回最新列表

    @log_api_call
    def github_get_subscribed(self):
        """获取所有已订阅的 Github 仓库"""
        records = list(GithubModRecord.select().dicts())
        for r in records:
            # 将缓存的字典暴露给前端的 online_info 字段
            r["online_info"] = r.get("online_info_cache", {})
        self._schedule_github_subs_refresh(records)

        return ApiResponse.success(records)

    def _schedule_github_subs_refresh(self, records: list) -> bool:
        """给 GitHub 订阅刷新加最短触发间隔，避免页面频繁打开时重复打满 API。"""
        if not records: return False

        now = current_ms()
        with self._github_subs_refresh_lock:
            if self._github_subs_refresh_running:
                logger.debug("GitHub 订阅后台刷新已在执行，跳过重复触发")
                return False
            if now - self._github_subs_refresh_started_at < GITHUB_SUBS_REFRESH_MIN_INTERVAL_MS:
                logger.debug("GitHub 订阅后台刷新距离上次启动过近，跳过本轮触发")
                return False
            self._github_subs_refresh_running = True
            self._github_subs_refresh_started_at = now

        started = self._start_tracked_main_db_task("github-subs-refresh", self._bg_refresh_github_subs, records)
        if started: return True

        with self._github_subs_refresh_lock:
            self._github_subs_refresh_running = False
        return False

    def _bg_refresh_github_subs(self, records: list):
        """
        后台多线程并发刷新 GitHub 数据
        """
        try:
            if not records: return
            
            updated_records = {}
            # 使用线程池并发请求 GitHub API，避免串行卡顿
            # 假设有 5 个订阅，5 个线程同时发请求，耗时取决于最慢的一个 (通常 < 500ms)
            def fetch_single(record):
                repo_url = record["repo_url"]
                source_branch = ""
                if str(record.get("install_type") or "").strip() == "source":
                    source_branch = str(record.get("target_branch") or "").strip()
                info = self.github_mgr.fetch_repo_info(repo_url, source_branch=source_branch)
                return repo_url, info
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as executor:
                # 提交所有任务
                futures = [executor.submit(fetch_single, r) for r in records]
                for future in futures:
                    try:
                        repo_url, info = future.result()
                        if "error" not in info:
                            updated_records[repo_url] = info
                    except Exception as e:
                        logger.error(f"后台刷新 GitHub Repo 失败: {e}", exc_info=True)

            # 如果没有成功获取到任何数据，直接结束
            if not updated_records: return
            # 批量更新数据库的缓存
            from backend.database.models import db, GithubModRecord
            import time
            current_time = int(time.time() * 1000)
            with db.atomic():
                for repo_url, info in updated_records.items():
                    GithubModRecord.update(
                        online_info_cache=info,
                        last_sync_time=current_time
                    ).where(GithubModRecord.repo_url == repo_url).execute()
            # 【核心】通过 EventBus 将最新数据推给前端 Vue
            EventBus.emit('github-online-update', updated_records)
            logger.info(f"后台 GitHub 数据刷新完成，已推送 {len(updated_records)} 条更新")
        finally:
            with self._github_subs_refresh_lock:
                self._github_subs_refresh_running = False

    @log_api_call
    def github_trigger_download(self, url: str, install_type: str, version: str):
        """触发下载与安装流程"""
        task_id = self.github_mgr.install_repo_mod(self.download_mgr, url, install_type, version)
        return ApiResponse.success({"task_id": task_id}, message="GitHub 部署任务已启动")

    @log_api_call
    def github_get_timeline(self, url: str):
        """获取某仓库的本地操作时间线"""
        logs = list(GithubTimeline.select().where(GithubTimeline.repo_url == url).order_by(GithubTimeline.time.desc()).dicts())
        result=[]
        title_map = {"subscribe": "订阅", "download": "下载", "update": "更新", "extract": "解压", "success":'部署成功', "error": "错误"}
        color_map = {"subscribe": "primary", "download": "info", "update": "tip", "extract": "info", "success": "success", "error": "danger"}
        for log in logs:
            result.append({
                "time": log["time"],
                "type": log["action"],
                "desc": log["message"],
                "title": title_map[log["action"]],
                "color": color_map[log["action"]],
            })
        return ApiResponse.success(result)
        
    @log_api_call
    def github_remove_subscription(self, url: str):
        """移除订阅，可选连带删除文件(前端应另行调用删除文件API)"""
        GithubModRecord.delete().where(GithubModRecord.repo_url == url).execute()
        GithubTimeline.delete().where(GithubTimeline.repo_url == url).execute()
        return ApiResponse.success(message="已移除订阅记录")
    
    
    # =========================================================================
    #  15. 贴图优化管理 (Texture Optimization)
    # =========================================================================
    
    def _resolve_mod_paths(self, package_ids: List[str]) -> List[str]:
        """内部辅助方法：将前端传来的 package_id 列表转换为当前环境下绝对物理路径列表"""
        target_tokens = [parse_package_token(pid) for pid in (package_ids or []) if pid]
        if not target_tokens: return []
        
        # 使用当前 Profile 上下文，确保获取的是正在使用的正确 Mod 路径 (解决软冲突路径)
        context_mods = ModDAO.get_profile_mods(self.active_context)
        mod_map = {
            normalize_package_id(m.get('package_id', '')): m
            for m in context_mods
            if normalize_package_id(m.get('package_id', ''))
        }
        paths = []
        seen_paths: set[str] = set()
        for token_info in target_tokens:
            mod = mod_map.get(token_info.canonical_package_id)
            if not mod:
                continue
            target_mod = mod
            if token_info.source_preference == "steam":
                target_mod = mod.get("coexist_workshop_variant") or mod
            path = str(target_mod.get('path') or '').strip()
            if path and path not in seen_paths:
                seen_paths.add(path)
                paths.append(path)
        return paths

    @log_api_call
    def texture_get_env_status(self, options: dict|None = None):
        """获取贴图优化工具状态"""
        try:
            status = self.texture_mgr.get_backend_status(options)
            return ApiResponse.success(status)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def texture_prepare_download(self, options: dict|None = None):
        """触发自动下载 todds"""
        try:
            res = self.texture_mgr.prepare_tool_download(self.download_mgr, options)
            if res.get("already_ready"):
                return ApiResponse.success(res, message="工具已经就绪")
            return ApiResponse.success(res, message="已启动工具下载任务")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ripgrep_prepare_download(self):
        """触发自动下载 ripgrep。"""
        try:
            from backend.text_search.tooling import prepare_ripgrep_download

            res = prepare_ripgrep_download(self.download_mgr, getattr(settings.config, "ripgrep_path", ""))
            if res.get("already_ready"):
                return ApiResponse.success(res, message="工具已经就绪")
            return ApiResponse.success(res, message="已启动 ripgrep 下载任务")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def texture_analyze_mods(self, package_ids: List[str], options: dict|None = None):
        """
        开始分析选中模组的贴图（多线程异步预热）
        """
        if not package_ids:
            return ApiResponse.error("未指定要分析的模组")
        
        paths = self._resolve_mod_paths(package_ids)
        if not paths:
            return ApiResponse.error("未能找到指定模组的有效物理路径")

        try:
            # 1. 直接先生成一个任务 ID 返回给前端，防止 pywebview Python主线程卡死
            task_id = uuid.uuid4().hex
            cancel_event = self.texture_mgr.register_analysis_task(task_id)
            
            def background_analyze():
                try:
                    self.texture_mgr.analyze_mods(
                        paths,
                        options,
                        task_id=task_id,
                        cancel_event=cancel_event,
                    )
                except TextureOptCancelled:
                    logger.info("后台贴图分析任务已取消")
                    self.texture_mgr._emit_analysis_progress(
                        task_id,
                        status="cancelled",
                        progress=0,
                        message="贴图扫描任务已取消",
                        processed_mods=0,
                        total_mods=len(paths),
                        summary=self.texture_mgr._create_empty_stat(include_mod_count=True, mod_count=len(paths)),
                    )
                except Exception as e:
                    logger.error(f"后台贴图分析任务执行失败: {e}", exc_info=True)
                finally:
                    self.texture_mgr.finish_analysis_task(task_id)

            # 2. 扔到守护后台线程去默默跑
            threading.Thread(target=background_analyze, daemon=True).start()

            return ApiResponse.success({"task_id": task_id}, message="贴图分析任务已在后台启动")
        except Exception as e:
            logger.error("贴图分析启动失败", exc_info=True)
            return ApiResponse.error(str(e))

    @log_api_call
    def texture_start_task(self, package_ids: List[str], action: str = "optimize", options: dict|None = None):
        """
        开始贴图优化或清理已生成 DDS
        :param action: "optimize" / "clean_generated"
        """
        # if not package_ids:
        #     return ApiResponse.error("未指定要处理的模组")
            
        paths = self._resolve_mod_paths(package_ids)
        if not paths:
            return ApiResponse.error("未能找到指定模组的有效物理路径")

        try:
            res = self.texture_mgr.start_task(paths, action=action, options=options)
            msg = "清理已生成 DDS" if action == "clean_generated" else "贴图优化"
            return ApiResponse.success(res, message=f"{msg}任务已加入队列")
        except Exception as e:
            logger.error("贴图优化任务启动失败", exc_info=True)
            return ApiResponse.error(str(e))

    @log_api_call
    def texture_cancel_task(self, task_id: str):
        """取消正在执行的贴图任务"""
        try:
            res = self.texture_mgr.cancel_task(task_id)
            return ApiResponse.success(res, message="正在尝试中止任务...")
        except Exception as e:
            return ApiResponse.error(str(e))

    
if __name__ == "__main__":
    # valid_field_names = set(UserModData._meta.fields.keys()) # type: ignore
    # print(valid_field_names)
    # steam_mgr=SteamManager()
    # installed_workshop_ids = steam_mgr.get_installed_workshop_ids()
    # print(len(installed_workshop_ids))
    # print(settings.config.community_instead_db_path)
    api=API()
    # api.update_external_db('workshop_db')
    # res = api.lifecycle_check_updates()
    # print(res)
    
    # res = api.lifecycle_fetch_collection("3670074636")
    # print(res)
    # res= api.texture_start_task([])
    res = api.get_mod_workshop_detail("3671245310", force_refresh=True)
    print(res)
    
    
    pass
