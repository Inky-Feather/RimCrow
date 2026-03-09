import asyncio
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import gc
import json
import os
import threading
import time
import functools
import uuid
from regex import E
import webview
from dataclasses import dataclass, asdict, is_dataclass
from typing import Any, Dict, List
from send2trash import send2trash
from datetime import datetime
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
from backend.settings import COMMUNITY_INSTEAD_DB_PATH, COMMUNITY_WORKSHOP_DB_PATH, DATA_DIR, HOME_DIR, settings, RULES_DIR
from backend.utils.event_bus import EventBus
from backend._version import __version__, __build__, get_all_changelogs
from backend.utils.tools import current_ms, generate_path_hash
from backend.utils.logger import logger
from backend.managers.mgr_network import network_mgr

# 2. 引入数据库层
from backend.database.models import ModAsset, UserModData, GithubModRecord, GithubTimeline, init_db, db
from backend.database.dao import CollectionDAO, ModDAO, GroupDAO
from backend.database.models_ext import WorkshopMeta, ext_db
from backend.database.dao_ext import ExtDAO

# 3. 引入业务逻辑管理器
from backend.scanner.parser_dlc import DLCParser
from backend.scanner.mod_scanner import ModScanner
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_files import FileManager, file_mgr, PathChecker
from backend.managers.mgr_game_logs import GameLogManager
from backend.managers.mgr_sorter import OrderSorter
from backend.managers.mgr_download import DownloadManager, TaskStatus
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_sub_browser import SubBrowserManager
from backend.managers.mgr_ai import AIManager
from backend.managers.mgr_workshop_db import WorkshopDBManager
# from backend.managers.mgr_workshop_db_old import WorkshopDBManager
from backend.managers.mgr_update import UpdateManager, UpdateInfo
from backend.managers.mgr_game_monitor import GameMonitor
from backend.managers.mgr_profile import ProfileContext, ProfileManager
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.managers.mgr_github import GithubManager
from playhouse.shortcuts import model_to_dict


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
        return asdict(cls(status="success", data=cls.serialize_data(data), message=message))

    @classmethod
    def error(cls, message, data=None):
        return asdict(cls(status="error", message=message, data=cls.serialize_data(data)))
    
    @classmethod
    def warning(cls, message, data=None):
        return asdict(cls(status="warning", message=message, data=cls.serialize_data(data)))
    
    @classmethod
    def serialize_data(cls, obj):
        if obj is None:
            return None
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


class API:
    """
    暴露给 pywebview 前端的统一接口类。
    所有前端调用的 window.pywebview.api.xxx 方法都在这里定义。
    """

    def __init__(self):
        logger.info("API Layer Initializing...")
        # 1. 初始化数据库
        # 数据库文件放在当前工作目录的data目录下
        db_path = str(DATA_DIR / 'mod_manager.db')
        self.is_first_db_init = not os.path.exists(db_path) # 标记是否首次初始化数据库
        init_db(db_path)
        # 当 pywebview 试图序列化 API 给 JS 用时，会试图深入序列化，
        # 公开属性会导致陷入无限递归（Window -> API -> Window -> ...），最终导致堆栈溢出崩溃
        self._window = None  # 私有属性
        self._upgrade_context = {
            "version_changed": False,
            "old_version": "0.0.0",
            "new_version": __version__,
            "actions_taken": [],      # 记录后端已经静默完成的操作
            "pending_actions": [],    # 记录需要前端配合的操作 (如 'show_news', 'force_scan')
            "messages": []            # 具体的提示文本
        }
        # 2. 实例化各个管理器
        self.workshop_db_mgr = WorkshopDBManager()
        self.game_mgr = GameManager()
        self.game_monitor = GameMonitor(self)
        self.profile_mgr = ProfileManager()
        self.active_context = None
        self.load_order_mgr = None
        self.scanner = None
        self.sorter = None
        # 3. 启动时激活上下文
        self._bootstrap_context(settings.config.current_profile_id)
        self.download_mgr = DownloadManager()
        self.github_mgr = GithubManager(self.download_mgr)
        self.file_mgr = FileManager()
        self.steam_mgr = SteamManager()
        self.steamcmd_controller = SteamCMDController(self.steam_mgr.steamcmd_exe)
        self.ai_mgr = AIManager()
        self.browser_window = SubBrowserManager(self)
        self.update_mgr = UpdateManager()
        
        # 每次启动 API 时，强制检查并修复 SteamCMD 的软链接！
        if settings.config.self_mods_path and settings.config.steamcmd_mods_path:
            FileManager.sync_steamcmd_root_link()
        
        # 执行升级检查
        self._handle_app_version_upgrade()
        logger.info("API Layer Ready.")
        
    
    def _bootstrap_context(self, profile_id: str):
        """装载当前环境，并重建所有业务引擎"""
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
        os.makedirs(settings.config.self_mods_path, exist_ok=True)
        
        # 依赖注入：将上下文发给所有的 Manager
        self.scanner = ModScanner(self.active_context)
        self.load_order_mgr = LoadOrderManager(self.active_context)
        self.game_log_mgr = GameLogManager(self.active_context)
        self.sorter = OrderSorter(self.active_context)

    def _handle_app_version_upgrade(self):
        """实例初始化时运行的升级逻辑"""
        from backend.database.models import SystemInfo
        last_ver_record = SystemInfo.get_or_none(SystemInfo.key == 'app_version')
        last_version = last_ver_record.value if last_ver_record else "0.17.9"
        current_version = __version__
        if last_version == current_version: return

        # 标记版本已变动
        self._upgrade_context["version_changed"] = True
        self._upgrade_context["old_version"] = last_version
        self._upgrade_context["changelog"] = get_all_changelogs()

        # --- 执行具体的升级任务 ---
        try:
            from distutils.version import LooseVersion
            # 这里不强制扫，而是给前端发一个信号
            if LooseVersion(last_version) < LooseVersion("0.17.10"): 
                self._upgrade_context["pending_actions"].append("recommend_scan")
                self._upgrade_context["messages"].append("检测到核心解析引擎升级，建议执行全量扫描以获得更好的兼容性。")
                self.ai_mgr.reset_system_prompts()  # 强制重置/同步 AI 提示词
                settings.set('community_workshop_db_path',str(COMMUNITY_WORKSHOP_DB_PATH))
                settings.set('community_instead_db_path',str(COMMUNITY_INSTEAD_DB_PATH))
            
            # 弹窗展示更新日志
            self._upgrade_context["pending_actions"].append("show_update_news")
            # --- 升级任务执行完毕，持久化新版本号 ---
            SystemInfo.insert(key='app_version', value=current_version).on_conflict_replace().execute()
            logger.info(f"应用升级处理完成: {last_version} -> {current_version}")

        except Exception as e:
            logger.error(f"Upgrade tasks failed: {e}")
    
    @log_api_call
    def get_changelog(self):
        """主动获取全量更新日志数据"""
        from backend._version import get_all_changelogs
        return ApiResponse.success(get_all_changelogs())
    
    def cleanup(self):
        """关闭数据库清理资源"""
        # 停止后台扫描任务 (如果有)
        if hasattr(self, 'scanner') and self.scanner: self.scanner.stop_scan() 
        # 停止游戏监控
        if self.game_monitor: self.game_monitor.running = False
        # 暂停所有事件发送
        EventBus.pause()
        from backend.database.models import close_db
        logger.info("Closing database connection...")
        close_db()
        # 强制杀死正在运行的 SteamCMD 进程
        if hasattr(self, 'steamcmd_controller') and self.steamcmd_controller:
            self.steamcmd_controller.kill_all()
        
    
    def set_window(self, window: webview.Window):
        """设置主窗口"""
        self._window  = window
        # 绑定 loaded 事件，确保窗口完全就绪后再启动监视器
        window.events.loaded += self._on_app_loaded
    
    def get_window(self):
        """获取主窗口"""
        return self._window
    
    def _on_app_loaded(self):
        """主窗口加载完毕回调"""
        # 确保只启动一次
        if not self.game_monitor.running:
            logger.info("UI已就绪，启动游戏监视器...")
            self.game_monitor.start()
    
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
    def monitor_frontend_ready(self):
        """前端 Vue 挂载完毕后，主动调用此接口通知后端"""
        EventBus.resume()
        EventBus.mark_ready() # 激活 EventBus
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
            "settings": asdict(settings.config), # 转为字典发给前端
            "asset_port": self.file_mgr.get_port(),
            "context_healthy": False, 
            "health_report": {},
            "all_mods": [],  # 返回过滤后的列表
            "groups": [],
            "active_load_order": [],
            "active_load_modify_time": 0,
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
        if self.load_order_mgr:
            active_load_order = self.load_order_mgr.read_active_mods()
        else:
            active_load_order = {'active_mods': [], 'modify_time': 0}
            
        replacements = self.workshop_db_mgr.get_replacements()
        replacements_map = {r['old_workshop_id']: r for r in replacements}
        
        dlc_parser = DLCParser(self.active_context.game_dlc_path)
        rule_mgr = self.sorter.rule_mgr if (self.sorter and self.sorter.rule_mgr) else None
        current_version = self.active_context.game_version[:3]
        
        # 5. 数据加工：注入翻译和图片 URL
        for mod in context_mods:
            # 翻译注入, 传入当前语言，Parser 内部会查找缓存
            if dlc_parser: dlc_parser.translate_record(mod, settings.config.language)
            # 注入清洗后的规则集
            if rule_mgr:
                mod['rules'] = rule_mgr.get_effective_mod_rules(mod['package_id'], mod)
            else:
                mod['rules'] = {}
            if mod['workshop_id'] and  mod['workshop_id'] in replacements_map:
                mod['replacement'] = replacements_map[mod['workshop_id']]
            else:
                mod['replacement'] = None
            # # 图片 URL 注入
            # pkg_id = mod['package_id']
            # # 优先使用物理路径（Source Path），即使它是被链接的 Workshop Mod
            # # 前端展示的是源文件的缩略图
            # preview_path = mod.get('preview_path')
            # icon_path = mod.get('icon_path')
            # # 1. 尝试获取已生成的缩略图路径 (物理路径)
            # thumb_path = file_mgr.get_thumbnail_path(pkg_id)
            # # 2. 决定列表图标 (优先用缩略图，没有则用原图)
            # list_thumb_path = thumb_path if thumb_path else preview_path
            # # 3. 转换为 HTTP URL
            # mod['thumb_url'] = file_mgr.get_asset_url(list_thumb_path) if list_thumb_path else None
            # # 4. 详情页大图 URL
            # mod['preview_url'] = file_mgr.get_asset_url(preview_path) if preview_path else None
            # # 5. 图标 URL
            # mod['icon_url'] = file_mgr.get_asset_url(icon_path) if icon_path else None
            
        result.update({
            "all_mods": context_mods,  # 返回过滤后的列表
            "groups": all_groups,
            "active_load_order": active_load_order.get('active_mods', []),
            "active_load_modify_time": active_load_order.get('modify_time', 0),
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
    
    @log_api_call
    def reset_database(self):
        """
        重置数据库：强制关闭连接，删除文件，重建。
        """
        import time
        from backend.database.models import db, init_db, clear_db
        
        try:
            # 1. 强制关闭连接
            if not db.is_closed():
                db.commit() # 主动提交一次事务，彻底释放 WAL 临时文件
                db.close()
            gc.collect() # 强制回收资源，确保文件句柄释放
            time.sleep(0.5) # 给操作系统一点缓冲时间
            # 关键：对于 SqliteExtDatabase，有时候即使 close 了，
            # 内部连接池可能还持有引用。如果是 Peewee，通常 close 足够。
            # 但为了保险，可以设为 None 或者再次 init。
            
            # 2. 定义文件路径
            db_dir = str(DATA_DIR)
            db_path = str(DATA_DIR / 'mod_manager.db')
            wal_path = db_path + '-wal'
            shm_path = db_path + '-shm'

            # 3. 尝试删除 (带重试机制，防止系统延迟释放)
            for _ in range(3):
                try:
                    if os.path.exists(db_path): os.remove(db_path)
                    if os.path.exists(wal_path): os.remove(wal_path)
                    if os.path.exists(shm_path): os.remove(shm_path)
                    break # 删除成功，跳出循环
                except PermissionError:
                    # 如果还是占用，等待 1s 重试
                    time.sleep(1)
            
            # 再次检查是否删除成功，若存在则尝试清空数据库
            if os.path.exists(db_path):
                result = clear_db()
                if not result:
                    return ApiResponse.error("清空数据库失败")

            self.is_first_db_init = True
            # 4. 重新初始化
            init_db(db_path)
            
            return ApiResponse.success({"message": "数据库已重置"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ApiResponse.error(str(e))
    
    @log_api_call
    def perform_database_cleanup(self):
        """手动触发：清理无效的 UserModData、GroupMod 和 ModAsset"""
        try:
            # 1. 清理文件已不存在的 ModAsset
            missing = ModDAO.find_missing_mods(delete=True)
            # 2. 清理孤立的用户数据和分组关联
            ModDAO.clean_orphaned_data()
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
    def get_default_community_paths(self):
        """获取默认的社区路径"""
        default_paths = settings.get_default_community_paths()
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
            if env_changed:
                logger.info("检测到核心路径变动，正在重新装配执行引擎...")
                # 重新调用 bootstrap，这会生成新的 ProfileContext 并重建所有 Manager
                self._bootstrap_context(pid)
            
            return ApiResponse.success({
                "settings": asdict(settings.config),
                "active_context": self.active_context # 这里的 serialize_data 会自动调用 to_dict
            }, message="配置保存成功")
            
        except Exception as e:
            logger.error(f"Save all settings failed: {str(e)}", exc_info=True)
            return ApiResponse.error(f"保存所有设置失败：{str(e)}")
    
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
        扫描完成后，Scanner 会自动根据当前 Profile 配置执行链接部署。
        立即返回状态，前端通过监听 'scan-progress' 和 'scan-complete' 事件获取更新。
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
                    # Profile 禁用了 Workshop (use_workshop_mods=False)，则不再扫描
                    if os.path.exists(cfg.workshop_mods_path) and \
                        (self.active_context.use_workshop_mods or self.active_context.profile_id=='default'):
                        paths_to_scan.append(cfg.workshop_mods_path)
                else:
                    return ApiResponse.error("当前 环境 未激活，无法扫描 Mods")
            if not paths_to_scan:
                return ApiResponse.error("没有配置有效的扫描路径")
            # 调用异步扫描
            # 注意：这里不需要 try-catch 包裹整个逻辑，因为异常在线程内被捕获并通过事件发回了
            # 1. 扫描所有路径入库
            # 2. 识别 Local vs Workshop 冲突
            # 3. 读取 settings.config.local_mods_path 和 workshop_mods_path
            # 4. 执行 FileManager.clear_links 部署软链接
            if not self.scanner: return ApiResponse.error("扫描器未初始化")
            result = self.scanner.scan_paths_async(paths_to_scan, forced_update=forced_update)
        except Exception as e:
            logger.error(f"Scan mods failed: {str(e)}", exc_info=True)
            return ApiResponse.error(f"扫描模组失败：{str(e)}")
        return ApiResponse.success({ "details": result },"后台扫描已启动")
    
    @log_api_call
    def scan_conflicts_resolve(self, operations: List[Dict]):
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
            # 开启事务，保证数据库操作的一致性
            with db.atomic():
                for op in operations:
                    action = op.get('action')
                    path = op.get('target_path')
                    keep_hash = op.get('keep_path_hash')
                    if not path: continue
                    success = False
                    msg = ""
                    if action == 'disable':
                        # 1. 执行物理与数据库禁用
                        success, msg = ModDAO.set_mod_disabled_status(path, disable=True)
                        # 2. 如果提供了保留项的 Hash，记录阴影路径
                        if success and keep_hash:
                            ModDAO.add_shadow_path(keep_hash, path)
                    elif action == 'delete':
                        # 执行物理删除
                        success, msg = ModDAO.delete_mod_physically(path)
                    results.append({
                        'path': path,
                        'status': 'success' if success else 'error',
                        'msg': msg if not success else ''
                    })
            return ApiResponse.success(results, "冲突处理完成")
        except Exception as e:
            return ApiResponse.error(f"处理出错: {str(e)}")
    
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
                ModDAO.set_mod_disabled_status(mod.path, disabled)
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
            result = ModDAO.link_mods(mod_ids)
            return ApiResponse.success(data=result)
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def mods_unlink(self, mod_ids: List[str]):
        """批量解除 Mod 联锁"""
        try:
            result = ModDAO.unlink_mods(mod_ids)
            return ApiResponse.success(data=result)
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
        :param mods_config_file_path: ModsConfig.xml 文件路径
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
            "modify_time": res.get('modify_time', 0)
        })
    
    @log_api_call
    def load_order_file_open(self, mods_config_file_path: str|None = None):
        """
        打开 ModsConfig.xml 文件
        """
        file = ''
        # 默认路径为 ModsConfig.xml 所在目录
        if not mods_config_file_path:
            mods_config_file_path = self.active_context.mods_config_file if self.active_context else ""
        # 检查路径是否合法，且是否为xml文件
        if os.path.isfile(mods_config_file_path) and (mods_config_file_path.endswith('.xml') or mods_config_file_path.endswith('.rws')):
            file = mods_config_file_path
        elif os.path.isdir(mods_config_file_path) :
            file = file_mgr.select_file_dialog(initial_dir=mods_config_file_path)
        else:
            file = file_mgr.select_file_dialog(initial_dir=self.active_context.game_config_path if self.active_context else "")
        if not file:
            return ApiResponse.warning("未选择文件")
        res = self.load_order_mgr.read_active_mods(file) if self.load_order_mgr else {}
        result = {
            "file": file,
            "active_ids": res.get('active_mods', []),
            "modify_time": res.get('modify_time', 0)
        }
        if not result["active_ids"]:
            return ApiResponse.error("解析文件出错!")
        return ApiResponse.success(result)
    
    @log_api_call
    def load_order_save(self, active_ids: List[str], is_dirty: bool=True):
        """
        保存当前激活列表到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        """
        if not self.active_context: return ApiResponse.error("环境配置上下文缺失")
        if not self.active_context.game_config_path or not os.path.exists(self.active_context.game_config_path): 
            return ApiResponse.error("未指定游戏配置路径")
        try:
            use_raw_ids = settings.config.use_raw_ids
            success = self.load_order_mgr.save_active_mods(active_ids, is_dirty=is_dirty, use_raw_ids=use_raw_ids) if self.load_order_mgr else False
            if success: return ApiResponse.success()
            return ApiResponse.warning("取消保存")
        except Exception as e:
            return ApiResponse.error(f"保存 ModsConfig.xml 时出错: {e}")
    
    @log_api_call
    def load_order_export(self, active_ids: List[str], target_path: str|None = None, trigger_dialog: bool = True):
        """
        导出当前加载顺序到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        :param target_path: 导出路径
        """
        try:
            if not target_path and not trigger_dialog: trigger_dialog = True
            success = self.load_order_mgr.save_active_mods(active_ids, target_path, trigger_dialog) if self.load_order_mgr else False
            if success: return ApiResponse.success()
            return ApiResponse.warning("取消保存")
        except Exception as e:
            return ApiResponse.error(f"导出加载顺序时出错: {e}")

    @log_api_call
    def backups_get_all(self):
        """获取所有备份文件路径"""
        try:
            backups = self.load_order_mgr.get_all_backups() if self.load_order_mgr else []
            return ApiResponse.success(backups)
        except Exception as e:
            return ApiResponse.error(f"获取备份文件时出错: {e}")
    
    @log_api_call
    def game_launch(self, profile_id: str):
        """启动游戏"""
        try:
            if not profile_id: profile_id = self.profile_mgr.current_profile.id
            if not profile_id: return ApiResponse.error("未指定 Profile ID")
            msg=''
            profile = self.profile_mgr.get_profile(profile_id)
            logger.debug(f"launch_game: profile_id={profile_id}, prefer_steam={settings.config.prefer_steam_launch}, steam_path={settings.config.steam_path}, is_steam={profile.is_steam}")
            # 检查 Steam 配置是否完整
            if(settings.config.prefer_steam_launch and profile.is_steam):
                # 1. 获取当前 Profile 的启动参数（仅包含游戏相关参数）
                extra_args = self.profile_mgr.get_launch_args_only(profile_id)
                logger.debug(f"launch_game_steam: extra_args={extra_args}")
                # 2. 调用 Steam 管理器启动游戏
                self.steam_mgr.launch_via_steam_cmd(extra_args=extra_args)
                msg='通过 Steam 启动游戏'
            else:
                # 1. 获取当前 Profile 的启动参数
                launch_args = self.profile_mgr.get_launch_args_only(profile_id) 
                logger.debug(f"launch_game: launch_args={launch_args}")
                # 2. 调用游戏管理器启动游戏
                self.game_mgr.launch_game(game_install_path=profile.game_install_path, custom_args=launch_args)
                msg='直接启动游戏'
            
            # 3. 记录最后一次游玩时间到数据库
            self.profile_mgr.update_profile(profile_id, {
                "last_played_time": current_ms()
            })
            return ApiResponse.success(message=f"{msg}成功，祝你游玩愉快！")
        except Exception as e:
            logger.error(f"Launch Game Error: {e}")
            return ApiResponse.error(f"启动游戏时出错: {e}")
    

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
            logger.error(f"Check Paths Error: {e}")
            return ApiResponse.error(f"检查路径时出错: {e}")
    
    @log_api_call
    def path_open(self, path: str):
        try:
            file_mgr.open_in_explorer(path)
            logger.info(f"打开路径: {path}")
            return ApiResponse.success()
        except Exception as e:
            logger.error(f"打开路径时出错: {e}")
            return ApiResponse.error(f"打开路径时出错: {e}")
    
    @log_api_call
    def path_delete(self, path: str):
        """删除文件/文件夹"""
        try:
            success = file_mgr.delete_path(path)
            if success: return ApiResponse.success()
            return ApiResponse.warning("路径不存在或无法删除")
        except Exception as e:
            return ApiResponse.error(f"删除路径时出错: {e}")
    
    @log_api_call
    def paths_delete(self, paths: List[str]):
        """批量删除文件/文件夹"""
        try:
            success_count, error_list = file_mgr.delete_paths(paths)
            if success_count == len(paths):
                return ApiResponse.success()
            return ApiResponse.warning(f"成功删除 {success_count} 个路径，{len(error_list)} 个路径删除失败")
        except Exception as e:
            return ApiResponse.error(f"批量删除路径时出错: {e}")
    
    @log_api_call
    def folder_select_dialog(self, initial_dir: str = ''):
        """
        打开系统原生的文件夹选择框
        """
        try:
            folder = file_mgr.select_folder_dialog(initial_dir)
            if folder:
                return ApiResponse.success(folder)
        except Exception as e:
            return ApiResponse.error(f"选择文件夹时出错: {e}")
        return ApiResponse.warning("未选择文件夹")
    
    @log_api_call
    def file_select_dialog(self, initial_dir: str = '', file_types = ('XML Files (*.xml;*.rws)', 'All Files (*.*)')):
        """
        打开系统原生的文件选择框
        """
        try:
            file = file_mgr.select_file_dialog(initial_dir, file_types)
            if file:
                return ApiResponse.success(file)
        except Exception as e:
            return ApiResponse.error(f"选择文件时出错: {e}")
        return ApiResponse.warning("未选择文件")

    @log_api_call
    def file_save_dialog(self, initial_dir: str = '', file_types = ('XML Files (*.xml;*.rws)', 'All Files (*.*)')):
        """
        打开系统原生的文件保存框
        """
        try:
            file = file_mgr.save_file_dialog(initial_dir, file_types)
            if file:
                return ApiResponse.success(file)
        except Exception as e:
            return ApiResponse.error(f"保存文件时出错: {e}")
        return ApiResponse.warning("未选择文件")
    
    @log_api_call
    def localize_workshop_mods(self, mod_ids: List[str], store: str = 'workshop'):
        """
        将工坊模组转为本地模组，并推送实时进度
        """
        cfg = settings.config
        local_root = self.active_context.local_mods_path if self.active_context else ""
        if not local_root:
            return ApiResponse.error("未指定本地模组路径")
        
        # 1. 准备任务 (使用 JOIN 一次性查出所有需要的数据)
        # 这里的退回顺序逻辑直接在 Python 循环中处理，清晰易维护
        query = (ModAsset.select(ModAsset, UserModData.alias_name)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
            .where(ModAsset.package_id << [mid.lower() for mid in mod_ids], ModAsset.store == store) # type: ignore
            .dicts())
        try:
            # 2. 执行任务
            res = file_mgr.localize_workshop_mods(query, local_root, cfg.coexist_mod_folder_name_type)
            if not res: return ApiResponse.warning(f"没有可转换的{store}模组")
        except Exception as e:
            logger.error(f"Localize workshop mods failed: {e}", exc_info=True)
            return ApiResponse.error(f"本地化任务失败: {str(e)}")
        
        return ApiResponse.success(message="本地化任务已在后台启动")
    
    @log_api_call
    def workspace_transfer_mods(self, path_hashes: list, target_store: str, mode: str = 'copy'):
        """
        跨库转移模组 (复制 / 移动)
        :param target_store: 'local' 或 'self'
        :param mode: 'copy' 或 'move'
        """
        if not self.active_context: 
            return ApiResponse.error("未指定环境")
        # 1. 拦截非法目标
        if target_store == 'workshop':
            return ApiResponse.error("为了保证 Steam 同步机制不被破坏，禁止手动向创意工坊目录导入文件。")
        # 2. 确定目标根目录
        target_root = ""
        if target_store == 'local':
            target_root = self.active_context.local_mods_path
        elif target_store == 'self':
            target_root = settings.config.self_mods_path
        if not target_root or not os.path.exists(target_root):
            return ApiResponse.error(f"目标库 {target_store} 的目录未配置或不存在！")
        # 3. 查出源文件信息
        from backend.database.models import ModAsset
        source_mods = ModAsset.select(ModAsset.path, ModAsset.package_id, ModAsset.store, ModAsset.name).where(ModAsset.path_hash.in_(path_hashes)).dicts() # type: ignore
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
            result = self.sorter.sort(active_ids) if self.sorter else {}
            if not result: return ApiResponse.error("排序失败, 排序引擎未初始化")
            # result 包含: sorted_ids, auto_activated, warnings
            msg = "排序完成"
            if result.get('auto_activated'):
                msg += f" (自动激活了 {len(result['auto_activated'])} 个联锁项)"
            
            return ApiResponse.success(result, msg)
        except Exception as e:
            logger.error(f"Auto sort failed: {e}", exc_info=True)
            return ApiResponse.error(f"排序失败: {str(e)}")
    
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
        弹出对话框并导出
        file_types 在前端调用时也可以不传，这里给默认值
        """
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            bundle = self.sorter.rule_mgr.create_export_bundle(dynamic_rule_ids)
            if not initial_dir: initial_dir = str(RULES_DIR)
            # 使用时间戳作为默认文件名
            default_name = f"RimOrder_Rules_{datetime.now().strftime('%Y%m%d')}.json"
            # 注意: file_types 参数格式需要符合 pywebview 的要求
            path = file_mgr.save_file_dialog(
                initial_dir=initial_dir, 
                default_filename=default_name, 
                file_types=('JSON Files (*.json)', 'All Files (*.*)')
            )
            
            if path:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(bundle, f, indent=4, ensure_ascii=False)
                return ApiResponse.success(message="导出成功")
            return ApiResponse.warning("已取消")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return ApiResponse.error(str(e))

    @log_api_call
    def rule_import_bundle(self):
        """弹出对话框并导入"""
        if not self.sorter or not self.sorter.rule_mgr:
            return ApiResponse.error("规则引擎未初始化")
        try:
            path = file_mgr.select_file_dialog(file_types=('JSON Files (*.json)',))
            if path:
                with open(path, 'r', encoding='utf-8') as f:
                    bundle = json.load(f)
                
                self.sorter.rule_mgr.process_import_bundle(bundle)
                return ApiResponse.success(message="规则包导入成功")
            return ApiResponse.warning("已取消")
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return ApiResponse.error(f"导入失败: {e}")
    
    @log_api_call
    def update_community_rule(self):
        """
        更新社区规则库
        """
        try:
            # 1. 路径准备
            # 注意：settings.config.community_rules_path 是完整文件路径 (例如 .../rules/community.json)
            full_path = settings.config.community_rules_path
            file_folder = os.path.dirname(full_path)
            file_name = os.path.basename(full_path)
            url = settings.config.community_rules_url
            
            if not os.path.exists(file_folder):
                os.makedirs(file_folder, exist_ok=True)

            logger.info(f"Start updating community rules from: {url}")
            # 定义回调函数：下载完了自动加载规则
            def on_rules_ready(task):
                if not self.sorter or not self.sorter.rule_mgr:
                    EventBus.send_toast("规则引擎未初始化，无法加载社区规则库", type="warning")
                else:
                    logger.info("Rules ready, reloading...")
                    self.sorter.rule_mgr.load_all()
                    EventBus.send_toast("社区规则库更新完毕！", type="success")
            
            def on_rules_error(task):
                logger.error(f"Rules download failed: {task.error_msg}")
                EventBus.send_toast("社区规则库更新失败！", type="error")

            task_id = self.download_mgr.add_task(
                url=url, 
                dest_dir=file_folder, 
                filename=file_name,
                on_complete=on_rules_ready,
                on_error=on_rules_error
            )

            return ApiResponse.success(data={"task_id": task_id}, message="社区规则库开始更新")
            
        except Exception as e:
            logger.error(f"Update community rules failed: {e}")
            return ApiResponse.error(f"系统错误: {str(e)}")

    
    # =========================================================================
    #  8. 日志管理 (Log Management)
    # =========================================================================

    @log_api_call
    def get_game_log_files(self):
        """ 获取游戏日志文件列表 """
        try:
            files = self.game_log_mgr.get_log_files() if self.game_log_mgr else []
            return ApiResponse.success(files)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def read_game_log(self, filename: str):
        """ 读取并解析指定的游戏日志 """
        # 这是一个可能耗时的操作，@log_api_call 会帮记录耗时
        result = self.game_log_mgr.read_and_parse_log(filename) if self.game_log_mgr else {'error': '游戏日志管理器未初始化'}
        if 'error' in result:
            return ApiResponse.error(result['error'])
        return ApiResponse.success(result)
    
    @log_api_call
    def open_log_folder(self):
        """ 打开日志所在文件夹 """
        path = self.active_context.user_data_path if self.active_context else None
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
    def download_cancel(self, task_id: str):
        self.download_mgr.cancel_task(task_id)
        return ApiResponse.success(message="尝试取消任务")

    @log_api_call
    def get_active_downloads(self):
        """获取所有任务状态 (用于 UI 恢复)"""
        return ApiResponse.success(self.download_mgr.get_tasks_info())
    
    @log_api_call
    def open_sub_browser(self, url='', title = 'RimModManager'):
        """打开或更新 浏览器子窗口"""
        if not self.browser_window: 
            self.browser_window = SubBrowserManager(self)
        self.browser_window.open(url, title)


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
            logger.error(f"Check update failed: {e}")
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
            logger.error(f"Update action failed: {e}")
            return ApiResponse.error(str(e))

    @log_api_call
    def update_ignore_version(self, version_str):
        """跳过当前版本"""
        settings.set('ignored_update_version', version_str)
        return ApiResponse.success()
    
    
    # =========================================================================
    #  11. Steam 集成 (Steam Integration)
    # =========================================================================

    @log_api_call
    def check_steam_tools(self):
        """
        前端初始化时调用，检查工具是否就绪。
        如果有缺失，自动触发下载任务。
        """
        # 1. 检查缺失文件并添加下载任务
        tasks = self.steam_mgr.ensure_tools(self.download_mgr)
        
        # 2. 如果有新任务，注册一个回调来处理下载后的解压/部署
        if tasks:
            # 需要一个简单的方法来监控这些任务的完成
            # 这里简化处理：启动一个后台线程轮询这些任务状态
            threading.Thread(target=self._monitor_setup_tasks, args=(tasks,), daemon=True).start()
            
        return ApiResponse.success({
            "steamcmd_ready": self.steam_mgr.steamcmd_ready,
            "pending_tasks": tasks
        })

    def _monitor_setup_tasks(self, tasks):
        """(内部) 监控工具下载任务，完成后执行安装逻辑"""
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
                    logger.error(f"Setup task failed: {task_id}")
                    pending.remove(item)
        # 初始化
        is_initialized = (Path(settings.config.steamcmd_path) / "public").exists()
        if os.path.exists(self.steamcmd_controller.steamcmd_exe) and not is_initialized:
            controller = SteamCMDController(self.steamcmd_controller.steamcmd_exe)
            def on_progress(percent, msg):
                # 将进度推给前端
                from backend.utils.event_bus import EventBus
                EventBus.emit('steamcmd-init-progress', {'percent': percent, 'msg': msg})
            success, msg = controller.initialize_steamcmd(on_progress)
            if not success:
                logger.error(f"SteamCMD 初始化彻底失败: {msg}")

    @log_api_call
    def steam_subscribe(self, workshop_ids: str):
        """调用 Steam 客户端订阅"""
        # 前置拦截
        if not self.steam_mgr.is_steam_running():
            return ApiResponse.warning("Steam 客户端未运行", data={"action": "need_start_steam"})
        try:
            success = self.steam_mgr.subscribe_items(workshop_ids)
            if success:
                return ApiResponse.success(message="已发送订阅请求 (需Steam运行中)")
            else:
                return ApiResponse.error("操作失败：SteamAPI 未就绪 (请确保Steam已运行)")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def steam_unsubscribe(self, workshop_ids: str):
        """调用 Steam 客户端取消订阅"""
        # 前置拦截
        if not self.steam_mgr.is_steam_running():
            return ApiResponse.warning("Steam 客户端未运行", data={"action": "need_start_steam"})
        try:
            success = self.steam_mgr.unsubscribe_items(workshop_ids)
            if success:
                return ApiResponse.success(message="已发送取消订阅请求")
            else:
                return ApiResponse.error("操作失败：SteamAPI 未就绪")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def steam_cancle_task(self, task_id):
        """取消 Steam 客户端任务"""
        success = self.steam_mgr.abort_monitor_task(task_id)
        if success:
            return ApiResponse.success(message="已取消任务")
        else:
            return ApiResponse.error("操作失败：SteamAPI 未就绪")
    
    @log_api_call
    def steam_launch_client(self):
        """前端主动调用唤醒 Steam"""
        success = self.steam_mgr.start_steam()
        if success:
            return ApiResponse.success(message="正在唤起 Steam 客户端，请等待其完全加载...")
        return ApiResponse.error("无法定位 Steam 路径，请手动打开！")
    
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
            self.steam_mgr.download_workshop_items(workshop_ids)
            return ApiResponse.success(message="SteamCMD 下载任务已启动")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    # =========================================================================
    #  12. AI 功能 (AI Features)
    # =========================================================================

    @log_api_call
    def ai_get_config(self):
        """获取当前 AI 配置和 Prompt 列表"""
        from backend.settings import AIConfig
        ai_cfg = settings.config.ai
        # 如果是字典，先转成对象，方便统一调用 asdict
        if isinstance(ai_cfg, dict):
            ai_cfg = AIConfig(**ai_cfg)
        return ApiResponse.success({
            "config": asdict(ai_cfg),
            "prompts": self.ai_mgr.prompts # 返回 prompt 定义，供前端生成动态表单
        })

    @log_api_call
    def ai_save_config(self, config_data: dict):
        """保存 AI 配置"""
        try:
            # 增量更新设置
            current_ai = settings.config.ai
            for k, v in config_data.items():
                if hasattr(current_ai, k):
                    setattr(current_ai, k, v)
            settings.save()
            return ApiResponse.success(message="AI 配置已保存")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_get_providers(self, api_type: str = "official"):
        """获取厂商或代理协议列表"""
        try:
            providers = self.ai_mgr.get_providers(api_type)
            return ApiResponse.success(providers)
        except Exception as e:
            return ApiResponse.error(f"获取厂商列表失败: {str(e)}")

    @log_api_call
    def ai_get_models(self, temp_config: dict):
        """
        获取模型列表
        自带缓存机制，极速响应。
        :param temp_config: 前端表单中的临时配置 {api_type, provider, base_url, api_key}
        """
        try:
            models = self.ai_mgr.get_models(temp_config)
            return ApiResponse.success(models)
        except Exception as e:
            return ApiResponse.error(f"获取模型列表失败: {str(e)}")

    @log_api_call
    def ai_chat(self, message: str, config_data: dict={}):
        """测试对话"""
        try:
            result = self.ai_mgr.test_chat(message, config_data)
            return ApiResponse.success(result)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def ai_execute_task(self, task_key: str, params: dict):
        """
        执行特定任务 (翻译、日志分析等)
        前端调用示例: ai_execute_task('translation', {content: 'About RimWorld', target_lang: 'Chinese'})
        """
        try:
            result = self.ai_mgr.execute_task(task_key, params)
            return ApiResponse.success(result)
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def ai_execute_batch_task(self, task_key: str, items: list, variables: dict = {}):
        """
        发起异步批量 AI 任务。
        前端调用此接口后会立即返回 task_id，随后通过 EventBus 监听进度。
        """
        if not settings.config.ai.enabled:
            return ApiResponse.error("AI 功能未启用")
        if not variables: variables = {}
        # 1. 生成唯一的任务 ID，供前端监听特定频道
        task_event_id = str(uuid.uuid4())
        # 2. 定义后台运行的工作线程
        def background_worker():
            # 为这个新线程创建一个全新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 运行写好的批量调度引擎
                results = loop.run_until_complete(
                    self.ai_mgr.execute_batch_task_async(task_key, items, variables, task_event_id)
                )
                # 任务彻底完成后，发送 complete 事件
                EventBus.emit(f'ai-batch-complete', {
                    'task_event_id': task_event_id,
                    'status': 'success', 
                    'data': results
                })
                # 可选：可以直接在这里调用 ModDAO 批量入库
                # if results:
                #     self._save_ai_results_to_db(results)
            except Exception as e:
                logger.error(f"Background AI task failed: {e}", exc_info=True)
                EventBus.emit(f'ai-batch-complete', {
                    'task_event_id': task_event_id,
                    'status': 'error', 
                    'message': str(e)
                })
            finally:
                loop.close()

        # 3. 启动守护线程（不阻塞当前 pywebview 的请求）
        threading.Thread(target=background_worker, daemon=True).start()

        # 4. 立即返回响应给前端，让前端开始监听
        return ApiResponse.success({
            "task_event_id": task_event_id,
            "total_items": len(items)
        }, message="批量任务已在后台启动")
    
    @log_api_call
    def ai_get_prompts(self):
        """获取所有提示词"""
        return ApiResponse.success(self.ai_mgr.prompts)

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
    def ai_reset_prompts(self):
        """恢复默认提示词"""
        try:
            res = self.ai_mgr.reset_system_prompts()
            return ApiResponse.success(res)
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
                self.profile_activate(pid)
            return ApiResponse.success(message="配置已更新")
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def profile_delete(self, pid):
        try:
            self.profile_mgr.delete_profile(pid)
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
    
    
    # ==========================================
    #  14. 外置数据管理 (External Data)
    # ==========================================
    @log_api_call
    def update_external_db(self, data_type: str):
        """
        更新外置数据（例如工坊数据库和替代数据库）
        """
        try:
            if data_type == "workshop_db":
                # 1. 路径准备
                # 注意：settings.config.community_workshop_db_path 是完整文件路径 (例如 .../steamDB.json)
                full_path = settings.config.community_workshop_db_path
                file_folder = os.path.dirname(full_path)
                file_name = os.path.basename(full_path)
                url = settings.config.community_workshop_db_url
            elif data_type == "instead_db":
                # 1. 路径准备
                # 注意：settings.config.community_instead_db_path 是完整文件路径 (例如 .../replacements.json)
                full_path = settings.config.community_instead_db_path
                file_folder = os.path.dirname(full_path)
                file_name = os.path.basename(full_path)
                url = settings.config.community_instead_db_url
            else:
                return ApiResponse.error(f"无效的数据库类型 {data_type}")
            
            if not os.path.exists(file_folder):
                os.makedirs(file_folder, exist_ok=True)
            logger.info(f"Start updating community {data_type} from: {url}")
            # 定义回调函数
            def on_db_ready(task):
                logger.info(f"{data_type} ready, reloading...")
                self.workshop_db_mgr.load_all_cache()
                # 当 workshop_db 更新完毕时，通知规则系统重建关联缓存
                if data_type == "workshop_db" and self.sorter:
                    self.sorter.rule_mgr.build_workshop_rules()
                self.workshop_db_mgr.load_all_cache()
                # self.sorter.rule_mgr.load_all()
                EventBus.send_toast(f"社区 {data_type} 数据库更新完毕！", type="success")
            def on_db_error(task):
                logger.error(f"{data_type} download failed: {task.error_msg}")
                EventBus.send_toast(f"社区 {data_type} 数据库更新失败！", type="error")
            task_id = self.download_mgr.add_task(
                url=url, 
                dest_dir=file_folder, 
                filename=file_name,
                on_complete=on_db_ready,
                on_error=on_db_error
            )

            return ApiResponse.success(data={"task_id": task_id}, message=f"社区 {data_type} 数据库开始更新")
            
        except Exception as e:
            logger.error(f"Update community {data_type} failed: {e}")
            return ApiResponse.error(f"系统错误: {str(e)}")
    
    @log_api_call
    def lifecycle_check_updates(self):
        """
        生命周期核心：精准识别【工坊目录】与【管理器目录】各自的更新状态
        """
        # 1. 分别获取两个来源的本地状态 (来自 SteamManager 的解析结果)
        # workshop_merged_data 内部解析的是 Steam 客户端的 ACF/LOG
        workshop_local_data = self.steam_mgr.workshop_merged_data()
        # steamcmd_merged_data 内部解析的是 管理器目录下的 ACF/LOG (SteamCMD专用)
        manager_local_data = self.steam_mgr.steamcmd_merged_data()
        # 2. 收集所有需要查询的工坊 ID (去重)
        all_wids = set(workshop_local_data.keys()) | set(manager_local_data.keys())
        if not all_wids: return ApiResponse.success({"updates": []})
        # 3. 一次性从缓存/网络获取所有涉及 ID 的云端最新时间
        online_details, ids_to_fetch = SteamWebAPI.fetch_item_details(list(all_wids))
        updates_available = []
        # 4. 定义内部比对逻辑
        def compare_and_add(local_item, source_label):
            wid = local_item['workshop_id']
            online_info = online_details.get(wid)
            if not online_info: return
            # 本地时间取：ACF 记录时间 或 日志下载时间
            local_time = local_item.get('time_downloaded') or local_item.get('installed_version_time') or 0
            online_time = online_info.get('time_updated', 0)
            # 容差 1 小时。如果云端时间 > 本地时间，则标记
            if online_time > local_time + 3600 * 1000:
                updates_available.append({
                    "workshop_id": wid,
                    "title": online_info["title"],
                    "source": source_label, # 告诉前端是 'workshop' 还是 'manager' 需更新
                    "local_time": local_time,
                    "online_time": online_time,
                    "preview_url": online_info["preview_url"]
                })
        # 5. 执行两次独立比对
        for m in workshop_local_data.values():
            if m.get('is_installed'):
                compare_and_add(m, 'workshop')
        for m in manager_local_data.values():
            if m.get('is_installed'):
                compare_and_add(m, 'self')
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
                meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == self_wid)
                if meta and meta.dependencies_mods:
                    for dep_wid, dep_name in meta.dependencies_mods.items():
                        # 反查依赖项的包名看本地有没有装
                        dep_meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == dep_wid)
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
    def lifecycle_fetch_collection_old(self, collection_id: str):
        """
        合集解析与下载预检：一键解析合集，对比本地，返回哪些需下载、哪些已存在
        """
        # 1. 抓取合集信息
        coll_info, ids_to_fetch = SteamWebAPI.fetch_item_details([collection_id])
        if not coll_info: return ApiResponse.error("无法获取合集信息")
        # 2. 抓取子项列表
        child_wids = SteamWebAPI.fetch_collection_children(collection_id)
        if not child_wids: return ApiResponse.error("合集为空或解析失败")
        # 3. 获取子项详情
        children_details, ids_to_fetch = SteamWebAPI.fetch_item_details(child_wids)
        
        # print("合集信息:",coll_info)
        # print("子项 ID:",child_wids)
        # print("子项详情:",list(children_details.values())[:2])
        
        # 4. 对比本地 ACF 安装记录
        installed_wids = self.steam_mgr.get_installed_workshop_ids()
        installed_str_wids = set([str(w) for w in installed_wids])
        result_children = []
        for wid in child_wids:
            info = children_details.get(wid, {})
            result_children.append({
                "workshop_id": wid,
                "title": info.get("title", f"Mod {wid}"),
                "preview_url": info.get("preview_url", ""),
                "is_installed": wid in installed_str_wids
            })
        return ApiResponse.success({
            "collection": coll_info[collection_id],
            "children": result_children,
            "total": len(child_wids),
            "need_download": len([c for c in result_children if not c['is_installed']])
        })
    
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
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == str(workshop_id))
        replacement = None
        game_version = self.active_context.game_version if self.active_context else ''
        if meta: replacement = self.workshop_db_mgr.check_replacement(meta.package_id, game_version)
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
        meta_map = WorkshopMeta.select(WorkshopMeta.package_id, WorkshopMeta.workshop_id).where(WorkshopMeta.package_id.in_(package_ids)).dicts()
        if not meta_map: return ApiResponse.error("未找到对应的 WorkshopID")
        return ApiResponse.success(
            { meta['package_id']: meta['workshop_id'] for meta in meta_map }
        )
    
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
        
        install_workshop_ids = set()
        # install_self_ids = set()
        
        # 3. 为已有的物理模组注入 Steam 状态
        for mod in matrix['workshop']:
            wid = str(mod.get('workshop_id'))
            if mod.get('path'): install_workshop_ids.add(wid)
            # 将 Steam 状态（订阅时间、真实下载时间等）直接合并进 mod 字典
            # 为了前端方便，把这些信息放在 'steam_info' 字段下，或者直接扁平化合并
            if wid in ws_map: mod['steam_status'] = ws_map[wid]
            mod['is_missing'] = False # 初始化标记
        
        # 为 self (管理器) 域注入数据
        for mod in matrix['self']:
            wid = str(mod.get('workshop_id'))
            # if mod.get('path'): install_self_ids.add(wid)
            if wid in mg_map: mod['steam_status'] = mg_map[wid]
            mod['is_missing'] = False
        
        for mod in matrix['local']:
            mod['is_missing'] = False
        
        # 4. 核心逻辑：找出“已订阅但物理丢失”的模组 (Ghost Mods)
        # 找出 ACF 中标记已订阅，但物理文件没被扫描到的 ID
        ghost_ws_ids = set([wid for wid, data in ws_map.items() if data.get('is_subscribed')]) - install_workshop_ids
        # ghost_self_ids = set([wid for wid, data in mg_map.items() if data.get('is_subscribed')]) - install_self_ids
        
        # 5. 从 ExtDB (外置社区库) 中获取这些幽灵模组的信息，使其在 UI 上能显示名字和图片
        all_ghost_ids = list(ghost_ws_ids)
        ghost_meta_map = {}
        if all_ghost_ids:
            from backend.database.models_ext import WorkshopMeta
            metas = WorkshopMeta.select(WorkshopMeta.workshop_id, WorkshopMeta.name, WorkshopMeta.preview_url).where(WorkshopMeta.workshop_id.in_(all_ghost_ids)).dicts()
            ghost_meta_map = {str(m['workshop_id']): m for m in metas}

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
                "steam_status": steam_status
            }
        for wid in ghost_ws_ids:
            matrix['workshop'].append(create_ghost(wid, 'workshop', ws_map.get(wid)))
            
        res = {
            "workshop": matrix['workshop'],
            "self": matrix['self'],
            "local": matrix['local']
        }
        
        # 6. 后台触发在线比对，标记可更新状态
        # 获取所有涉及的 WID
        all_wids = list(ws_map.keys()) + list(mg_map.keys())
        import threading
        threading.Thread(target=self._bg_check_online_updates, args=(all_wids,), daemon=True).start()

        return ApiResponse.success(res)
    
    def _bg_check_online_updates(self, all_wids: list):
        """后台静默检测，完成后通过 EventBus 推送"""
        online_info, ids_to_fetch = SteamWebAPI.fetch_item_details(all_wids, only_cache=True)
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
        def worker():
            from backend.managers.mgr_steam_api import SteamWebAPI
            from backend.utils.event_bus import EventBus
            
            # 100 个一组分批请求，防止 URL 过长或单次请求过久
            for i in range(0, len(workshop_ids), 100):
                batch = workshop_ids[i:i+100]
                # 这里调用真实的联网请求
                online_data = SteamWebAPI.fetch_item_details(batch, force_refresh=True)
                
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
    def nexus_search(self, query: str, page: int = 1):
        """离线库搜索 + 在线静默预热"""
        # 1. 从本地 SQLite 获取当前页的数据 (瞬间完成)
        data = ExtDAO.search_nexus(query, page, page_size=100)
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
    def nexus_get_details(self, workshop_id: str):
        """获取云端详细图文"""
        details = SteamWebAPI.get_or_fetch_details(workshop_id)
        if details:
            return ApiResponse.success(details)
        return ApiResponse.error("未找到模组详情")

    
    
    
    # 收藏合集相关接口
    
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
    def lifecycle_fetch_collection(self, collection_id: str):
        """
        合集加载引擎 (分步模式)：
        1. 立即从数据库返回缓存数据 (包含上一次的子项快照)
        2. 启动后台线程，执行：网络解析 -> 状态对比 -> 存库 -> EventBus 通知刷新
        """
        coll_id = str(collection_id)
        
        # --- 第一阶段：同步返回缓存 ---
        cached_coll = CollectionDAO.get_collection_by_id(coll_id)
        
        # 即使有缓存，我们也需要根据当前本地文件实时修正 is_installed 状态
        # 否则用户刚下完 Mod，点开合集显示的还是旧的“未安装”
        initial_data = None
        if cached_coll:
            # 实时计算安装状态 (基于快照)
            workshop_installed = self.steam_mgr.get_installed_workshop_ids()
            manager_installed_ids = [int(m['workshop_id']) for m in self.steam_mgr.steamcmd_merged_data().values() if m.get('is_installed')]
            all_installed_set = set([str(wid) for wid in (list(workshop_installed) + manager_installed_ids)])
            
            processed_children = []
            for child in (cached_coll.children or []):
                child['is_installed'] = child['workshop_id'] in all_installed_set
                processed_children.append(child)
            
            initial_data = {
                "collection": model_to_dict(cached_coll),
                "children": processed_children,
                "total": cached_coll.total,
                "need_download": len([c for c in processed_children if not c['is_installed']]),
                "is_cache": True # 标记这是缓存
            }

        # --- 第二阶段：启动异步更新任务 ---
        # 无论是否有缓存，都在后台刷一遍最新的
        threading.Thread(target=self._bg_refresh_collection, args=(coll_id,), daemon=True).start()

        return ApiResponse.success(initial_data)

    def _bg_refresh_collection(self, coll_id: str):
        """后台刷新任务 (网络密集 + 数据库写入)"""
        try:
            logger.debug(f"开始后台刷新合集: {coll_id}")
            # 1. 抓取最新子项 ID 列表
            child_wids = SteamWebAPI.fetch_collection_children(coll_id)
            
            # 2. 抓取所有项（含合集本身）的最新详情 (利用你新改的 fetch_item_details)
            # 这里的 batch_ids 包含合集 ID 自己
            all_ids = list(set([coll_id] + child_wids))
            online_results, _ = SteamWebAPI.fetch_item_details(all_ids, force_refresh=True)
            
            if coll_id not in online_results: return
            main_info = online_results[coll_id]

            # 3. 反查 PackageID
            from backend.database.models_ext import WorkshopMeta
            meta_records = WorkshopMeta.select(WorkshopMeta.workshop_id, WorkshopMeta.package_id).where(WorkshopMeta.workshop_id.in_(child_wids))
            pid_map = {str(m.workshop_id): m.package_id for m in meta_records}

            # 4. 计算安装状态
            workshop_installed = self.steam_mgr.get_installed_workshop_ids()
            manager_installed_ids = [int(m['workshop_id']) for m in self.steam_mgr.steamcmd_merged_data().values() if m.get('is_installed')]
            all_installed_set = set([str(wid) for wid in (list(workshop_installed) + manager_installed_ids)])

            # 5. 组装并准备持久化
            final_children = []
            for wid in child_wids:
                info = online_results.get(wid, {})
                final_children.append({
                    "workshop_id": wid,
                    "package_id": pid_map.get(wid),
                    "title": info.get("title", f"Mod {wid}"),
                    "preview_url": info.get("preview_url", ""),
                    "is_installed": wid in all_installed_set
                })

            total = len(final_children)
            missing = len([c for c in final_children if not c['is_installed']])

            # 6. 存入数据库
            CollectionDAO.upsert_collection(coll_id, main_info, final_children, total, missing)

            # 7. 通过 EventBus 通知前端：数据已就绪，请刷新
            EventBus.emit('workspace-collection-updated', {
                "id": coll_id,
                "data": {
                    "collection": main_info,
                    "children": final_children,
                    "total": total,
                    "need_download": missing,
                    "is_cache": False
                }
            })
            logger.debug(f"后台刷新合集完成: {coll_id}")

        except Exception as e:
            logger.error(f"后台刷新合集失败: {e}", exc_info=True)
    
    # GitHub 相关接口
    
    @log_api_call
    def github_fetch_info(self, url: str):
        """解析并获取远程仓库信息"""
        res = self.github_mgr.fetch_repo_info(url)
        if "error" in res: return ApiResponse.error(res["error"])
        return ApiResponse.success(res)

    @log_api_call
    def github_subscribe(self, payload: dict):
        """添加订阅到数据库"""
        url = payload.get("url")
        if not url: return ApiResponse.error("URL 不能为空")
        
        with db.atomic():
            record, created = GithubModRecord.get_or_create(
                repo_url=url,
                defaults={
                    "owner": payload.get("owner"),
                    "repo_name": payload.get("repo"),
                    "target_branch": payload.get("default_branch"),
                    "install_type": payload.get("install_type", "source")
                }
            )
            # 如果是新建的，写入初始日志
            if created:
                self.github_mgr.record_timeline(url, "subscribe", "已添加 GitHub 仓库监听记录")
        return self.github_get_subscribed() # 返回最新列表

    @log_api_call
    def github_get_subscribed(self):
        """获取所有已订阅的 Github 仓库"""
        records = list(GithubModRecord.select().dicts())
        for r in records:
            # 将缓存的字典暴露给前端的 online_info 字段
            r["online_info"] = r.get("online_info_cache", {})
        # 2. 启动后台静默更新线程 (不阻塞当前请求)
        threading.Thread(target=self._bg_refresh_github_subs, args=(records,), daemon=True).start()

        return ApiResponse.success(records)

    def _bg_refresh_github_subs(self, records: list):
        """
        后台多线程并发刷新 GitHub 数据
        """
        if not records: return
        
        updated_records = {}
        # 使用线程池并发请求 GitHub API，避免串行卡顿
        # 假设有 5 个订阅，5 个线程同时发请求，耗时取决于最慢的一个 (通常 < 500ms)
        def fetch_single(record):
            repo_url = record["repo_url"]
            info = self.github_mgr.fetch_repo_info(repo_url)
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
                    logger.error(f"后台刷新 GitHub Repo 失败: {e}")

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

    @log_api_call
    def github_trigger_download(self, url: str, install_type: str, version: str):
        """触发下载与安装流程"""
        task_id = self.github_mgr.trigger_download(url, install_type, version)
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
    
    res = api.get_mod_workshop_detail("3671245310", force_refresh=True)
    print(res)
    
    
    pass