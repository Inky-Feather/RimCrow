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
import webview
from dataclasses import dataclass, asdict
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
from backend.settings import settings, RULES_DIR
from backend.utils.event_bus import EventBus
from backend._version import __version__, __build__
from backend.utils.tools import current_ms
from backend.utils.logger import logger

# 2. 引入数据库层
from backend.database.models import ModAsset, UserModData, init_db, db
from backend.database.dao import ModDAO, GroupDAO

# 3. 引入业务逻辑管理器
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_files import FileManager
from backend.scanner.parser_dlc import DLCParser
from backend.scanner.mod_scanner import ModScanner
from backend.managers.mgr_game_logs import GameLogManager
from backend.managers.mgr_sorter import OrderSorter
from backend.managers.mgr_network import NetworkManager
from backend.managers.mgr_download import DownloadManager, TaskStatus
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_sub_browser import SubBrowserManager
from backend.managers.mgr_ai import AIManager
from backend.managers.mgr_update import UpdateManager, UpdateInfo
from backend.managers.mgr_game_monitor import GameMonitor
from backend.managers.mgr_profile import ProfileManager


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
        # 1. 处理 Peewee 模型对象
        if isinstance(obj, Model):
            # recurse=True 自动处理关联表，但通常我们建议只转单表
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
        db_path = os.path.join(os.getcwd(), 'data', 'mod_manager.db')
        self.is_first_db_init = not os.path.exists(db_path) # 标记是否首次初始化数据库
        init_db(db_path)
        # 当 pywebview 试图序列化 API 给 JS 用时，会试图深入序列化，
        # 公开属性会导致陷入无限递归（Window -> API -> Window -> ...），最终导致堆栈溢出崩溃
        self._window = None  # 私有属性
        # 2. 实例化各个管理器
        self.dlc_parser = None # 延迟初始化
        self.file_mgr = FileManager()    # 实例化 FileManager (它会自动启动 Server 线程)
        self.game_mgr = GameManager()
        self.game_monitor = GameMonitor(self)
        self.profile_mgr = ProfileManager()
        self.game_log_mgr = GameLogManager()
        self.load_order_mgr = LoadOrderManager() # 内部会自动从 settings 读取路径
        self.scanner = ModScanner()
        self.sorter = OrderSorter()
        self.network_mgr = NetworkManager()
        self.download_mgr = DownloadManager()
        self.steam_mgr = SteamManager()
        self.ai_mgr = AIManager()
        self.browser_window = SubBrowserManager(self)
        self.update_mgr = UpdateManager()
        logger.info("API Layer Ready.")

    def _ensure_dlc_parser(self):
        """懒加载 DLC Parser"""
        if not self.dlc_parser and settings.config.game_dlc_path:
            dlc_dir = settings.config.game_dlc_path
            if os.path.exists(dlc_dir):
                # 这里初始化会自动处理全量缓存和增量更新
                self.dlc_parser = DLCParser(dlc_dir)
    def cleanup(self):
        """关闭数据库清理资源"""
        # 停止后台扫描任务 (如果有)
        if hasattr(self, 'scanner'): self.scanner.stop_scan() 
        # 停止游戏监控
        if self.game_monitor: self.game_monitor.running = False
        # 暂停所有事件发送
        EventBus.pause()
            
        from backend.database.models import close_db
        logger.info("Closing database connection...")
        close_db()
    
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
    
    
    # =========================================================================
    #  1. 初始化与全局数据 (Initialization)
    # =========================================================================
    @log_api_call
    def get_initial_data(self):
        """
        前端启动时调用，一次性获取所有必要数据。
        """
        # 1. 检查路径配置是否完善
        paths_valid = settings.validate_paths() if hasattr(settings, 'validate_paths') else False
        if not paths_valid and settings.config.game_install_path:
            # 非空检查兜底
            paths_valid = self.game_mgr.detect_executable(settings.config.game_install_path) is not None
        self._ensure_dlc_parser()   # 确保 DLC Parser 初始化
        # 初始化profile检查
        if settings.config.current_profile_id=='default' and not self.profile_mgr.get_current_profile().game_install_path:
            # 初始化默认profile
            self.profile_mgr.update_profile('default',{
                'name': 'Default',
                'description': 'Default profile',
                'game_version': settings.config.game_version,
                'game_install_path': settings.config.game_install_path,
                'user_data_path': settings.config.user_data_path,
                'use_workshop_mods': "steamlibrary" in settings.config.game_install_path.lower(),
            })
        
        # 2. 获取当前环境的 Mod 数据 (包含用户自定义数据), 并排除缺失的 Mod
        # 传入 None 让 DAO 自动读取 settings.current_profile_id
        # DAO 内部会自动处理：
        #   - 过滤掉非当前 Local 目录的 Mod
        #   - 过滤掉未启用 Workshop 环境下的 Workshop Mod
        #   - 执行 "Local 覆盖 Workshop" 的遮蔽策略
        context_mods = ModDAO.get_profile_mods() 
        # 3. 获取所有分组数据 (结构化)
        # 传入当前的 assets 列表 ID，用于过滤掉分组中存在但当前环境下不可见的 Mod
        current_assets_ids = [m['package_id'] for m in context_mods]
        all_groups = GroupDAO.get_groups_structured_by_mod_ids(current_assets_ids)
        # 4. 获取当前激活的加载顺序
        active_load_order = self.load_order_mgr.read_active_mods()
        
        # 5. 数据加工：注入翻译和图片 URL
        for mod in context_mods:
            # 翻译注入
            if self.dlc_parser:
                # 传入当前语言，Parser 内部会查找缓存
                self.dlc_parser.translate_record(mod, settings.config.language)
                
            # 注入清洗后的规则集
            mod['rules'] = self.sorter.rule_mgr.get_effective_mod_rules(mod['package_id'], mod)
            
            # 图片 URL 注入
            pkg_id = mod['package_id']
            # 优先使用物理路径（Source Path），即使它是被链接的 Workshop Mod
            # 前端展示的是源文件的缩略图
            preview_path = mod.get('preview_path')
            icon_path = mod.get('icon_path')
            
            # 1. 尝试获取已生成的缩略图路径 (物理路径)
            thumb_path = self.file_mgr.get_thumbnail_path(pkg_id)
            
            # 2. 决定列表图标 (优先用缩略图，没有则用原图)
            list_thumb_path = thumb_path if thumb_path else preview_path
            
            # 3. 转换为 HTTP URL
            mod['thumb_url'] = self.file_mgr.get_asset_url(list_thumb_path) if list_thumb_path else None
            
            # 4. 详情页大图 URL
            mod['preview_url'] = self.file_mgr.get_asset_url(preview_path) if preview_path else None
            
            # 5. 图标 URL
            mod['icon_url'] = self.file_mgr.get_asset_url(icon_path) if icon_path else None
                
        result = {
            "app_version": __version__,
            "build_mode": __build__,
            "paths_configured": paths_valid,
            "settings": asdict(settings.config), # 转为字典发给前端
            "all_mods": context_mods,  # 返回过滤后的列表
            "groups": all_groups,
            "active_load_order": active_load_order.get('active_mods', []),
            "active_load_modify_time": active_load_order.get('modify_time', 0),
            "is_first_db_init": self.is_first_db_init
        }
        if paths_valid and context_mods: 
            self.is_first_db_init = False   # 标记数据库已初始化
        return ApiResponse.success(result)
    
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
            # 但为了保险，我们可以设为 None 或者再次 init。
            
            # 2. 定义文件路径
            db_dir = os.path.join(os.getcwd(), 'data')
            db_path = os.path.join(db_dir, 'mod_manager.db')
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

    # =========================================================================
    #  2. 设置与路径 (Settings & Paths)
    # =========================================================================
    @log_api_call
    def auto_detect_paths(self, update_config: bool = True):
        """自动检测游戏路径"""
        result = self.game_mgr.auto_detect_paths()
        steam_exe_path = self.steam_mgr.get_steam_path()
        if not result: return ApiResponse.error("无法自动检测到游戏路径，请手动设置！")
        result['steam_exe_path'] = steam_exe_path if steam_exe_path else ''
        if update_config:   # 仅当请求时更新配置
            settings.update_paths(result)
        # 如果检测到了安装路径，自动更新设置
        if result.get('game_install_path'):
            # 重新初始化 LoadOrderManager (因为 Config 路径可能变了)
            self.load_order_mgr = LoadOrderManager()
            return ApiResponse.success({"paths": result})
        return ApiResponse.warning("仅检测到部分路径，请手动设置！",{"paths": result})

    @log_api_call
    def save_setting(self, key: str, value: Any):
        """保存单个设置项"""
        # 如果修改的是核心路径，同步到当前环境
        if key in ['game_install_path', 'user_data_path', 'use_workshop_mods', 'run_commands']:
            pid = settings.config.current_profile_id
            # 更新数据库中的 Profile
            updates = {key: value}
            if key == 'use_workshop_mods': updates = {'use_workshop_mods': value}
            self.profile_mgr.update_profile(pid, updates)
            # 应用并触发同步逻辑
            self.profile_mgr.activate_profile(pid)
        # 如果修改的是路径，可能需要刷新管理器
        elif 'path' in key:
            self.load_order_mgr = LoadOrderManager()
        else:
            settings.set(key, value)
        return ApiResponse.success(data=asdict(settings.config))

    @log_api_call
    def save_all_settings(self, settings_obj: dict):
        """保存所有设置 (前端设置面板保存时调用)"""
        # 批量更新
        for k, v in settings_obj.items():
            # 如果修改的是核心路径，同步到当前环境
            if k in ['game_install_path', 'user_data_path', 'use_workshop_mods', 'run_commands']:
                pid = settings.config.current_profile_id
                # 更新数据库中的 Profile
                updates = {k: v}
                if k == 'use_workshop_mods': updates = {'use_workshop_mods': v}
                self.profile_mgr.update_profile(pid, updates)
            settings.set(k, v) # settings.set 内部会自动 save，这里可能稍微有点IO冗余，但安全
        
        # 应用并触发同步逻辑
        self.profile_mgr.activate_profile(pid)
        # 刷新管理器
        self.load_order_mgr = LoadOrderManager()
        return ApiResponse.success(data=asdict(settings.config))
    

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
        paths_to_scan = []
        if specific_paths: paths_to_scan = specific_paths
        else:
            # 确保当前 Profile 已激活
            self.profile_mgr.activate_profile(settings.config.current_profile_id)
            # 根据 Settings 动态构建扫描路径
            cfg = settings.config
            # 1. DLC (Data 目录)
            if cfg.game_dlc_path and os.path.exists(cfg.game_dlc_path):
                dlc_path = cfg.game_dlc_path
                if os.path.exists(dlc_path):
                    paths_to_scan.append(dlc_path)
            # 2. Local Mods (当前环境的 Mods 目录)
            if cfg.local_mods_path and os.path.exists(cfg.local_mods_path):
                paths_to_scan.append(cfg.local_mods_path)
            # 3. Workshop Mods (公共工坊目录)
            # Profile 禁用了 Workshop (use_workshop_mods=False)，则不再扫描
            if cfg.workshop_mods_path and os.path.exists(cfg.workshop_mods_path) and cfg.use_workshop_mods:
                paths_to_scan.append(cfg.workshop_mods_path)
        if not paths_to_scan:
            return ApiResponse.error("没有配置有效的扫描路径")
        # 调用异步扫描
        # 注意：这里不需要 try-catch 包裹整个逻辑，因为异常在线程内被捕获并通过事件发回了
        # 1. 扫描所有路径入库
        # 2. 识别 Local vs Workshop 冲突
        # 3. 读取 settings.config.local_mods_path 和 workshop_mods_path
        # 4. 执行 FileManager.clear_links 部署软链接
        result = self.scanner.scan_paths_async(
            paths_to_scan, 
            thumbnail_mgr=self.file_mgr, 
            forced_update=forced_update
        )
        return ApiResponse.success({ "details": result },"后台扫描已启动")
    
    @log_api_call
    def update_mod_time(self, mods_data_list: List[Dict[str, Any]]):
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
    def update_mod_user_data(self, package_id: str, data_dict: dict):
        """
        即时保存用户对 Mod 的修改 (标签, 备注, 颜色等)
        """
        try:
            ModDAO.update_user_data(package_id, data_dict)
            return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def set_mods_ignore_issues(self, mods_data_list: List[Dict[str, Any]]):
        """
        批量更新用户对 Mod 的修改 (标签, 备注, 颜色等)
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
    def set_mods_color(self, mod_ids: List[str], color: str):
        """批量设置 Mod 颜色"""
        try:
            ModDAO.set_mods_color(mod_ids, color)
            return ApiResponse.success(message="颜色已设置")
        except Exception as e:
            return ApiResponse.error((mod_ids, color, str(e)))
    
    @log_api_call
    def set_user_mods_type(self, mod_ids: List[str], new_type: str):
        """批量设置用户自定义 Mod 类型"""
        try:
            ModDAO.set_user_mods_type(mod_ids, new_type)
            return ApiResponse.success(message="类型已设置")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def link_mods(self, mod_ids: List[str]):
        """批量设置 Mod 联锁"""
        try:
            result = ModDAO.link_mods(mod_ids)
            return ApiResponse.success(data=result)
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def unlink_mods(self, mod_ids: List[str]):
        """批量解除 Mod 联锁"""
        try:
            result = ModDAO.unlink_mods(mod_ids)
            return ApiResponse.success(data=result)
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def add_tags_to_mods(self, mod_ids: List[str], tags: List[str]):
        """批量添加标签"""
        try:
            ModDAO.add_tags_to_mods(mod_ids, tags)
            return ApiResponse.success(message="标签已添加")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def remove_tags_from_mods(self, mod_ids: List[str], tags: List[str]):
        """批量移除标签"""
        try:
            ModDAO.remove_tags_from_mods(mod_ids, tags)
            return ApiResponse.success(message="标签已移除")
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def batch_update_user_data(self, user_data_list: List[Dict[str, Any]]):
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
    def resolve_scan_conflicts(self, operations: List[Dict]):
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
            with db.atomic(): # 开启事务，确保文件和数据库操作的原子性
                for op in operations:
                    action = op.get('action')
                    target_path = op.get('target_path')
                    if not target_path or not os.path.exists(target_path):
                        results.append({'path': target_path, 'status': 'error', 'msg': '路径不存在'})
                        continue
                    if action == 'disable':
                        # 重命名 About.xml -> About.xml.disabled
                        about_xml = os.path.join(target_path, 'About', 'About.xml')
                        disabled_xml = os.path.join(target_path, 'About', 'About.xml.disabled')
                        # 检查 About.xml 是否存在
                        if os.path.exists(about_xml):
                            try:
                                # 如果目标已存在，先删除旧的disabled (极其罕见)
                                if os.path.exists(disabled_xml): os.remove(disabled_xml)
                                os.rename(about_xml, disabled_xml)
                                # 更新数据库状态为 disabled = True
                                ModAsset.update(disabled=True).where(ModAsset.path == target_path).execute()
                                # 尝试更新 shadow_paths，如果失败（Mod不存在）则忽略
                                # 因为下次扫描时，保留的 Mod 会入库。
                                keep_path_hash = op.get('keep_path_hash')
                                if keep_path_hash:
                                    self._add_shadow_path(keep_path_hash, target_path)
                                    
                                results.append({'path': target_path, 'status': 'success'})
                            except Exception as e:
                                logger.error(f"Disable mod failed: {e}")
                                results.append({'path': target_path, 'status': 'error', 'msg': str(e)})
                        else:
                            # 可能是 XML 已经不在了，但为了保险，标记数据库
                            ModAsset.update(disabled=True).where(ModAsset.path == target_path).execute()
                            results.append({'path': target_path, 'status': 'skipped', 'msg': 'About.xml not found'})

                    elif action == 'delete':
                        # 方案：移入回收站
                        try:
                            send2trash(os.path.abspath(target_path))
                            # 文件删除后，立刻从数据库彻底抹除记录
                            ModAsset.delete().where(ModAsset.path == target_path).execute()
                            results.append({'path': target_path, 'status': 'success'})
                        except Exception as e:
                            results.append({'path': target_path, 'status': 'error', 'msg': str(e)})

            return ApiResponse.success(results, "冲突处理完成")
        except Exception as e:
            return ApiResponse.error(f"处理出错: {str(e)}")
    
    def _add_shadow_path(self, keep_path_hash: str, path: str):
        """辅助方法：更新 Mod 的 shadow_paths 字段"""
        try:
            mod = ModAsset.get_or_none(ModAsset.path_hash == keep_path_hash)
            if mod:
                # 获取现有列表 (peewee JSON field 自动反序列化)
                current_paths = mod.shadow_paths or []
                if path not in current_paths:
                    current_paths.append(path)
                    mod.shadow_paths = current_paths
                    mod.save()
        except Exception as e:
            logger.error(f"Error updating shadow paths: {e}")
    
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
    #  4. 分组管理 (Groups) - 即时保存
    # =========================================================================

    @log_api_call
    def get_groups(self):
        context_mods = ModDAO.get_profile_mods() 
        # 传入当前的 assets 列表 ID，用于过滤掉分组中存在但当前环境下不可见的 Mod
        current_assets_ids = [m['package_id'] for m in context_mods]
        return ApiResponse.success(GroupDAO.get_groups_structured_by_mod_ids(current_assets_ids))

    @log_api_call
    def create_group(self, name: str, color: str):
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
    def delete_group(self, group_id: str):
        return ApiResponse.success(GroupDAO.delete_group(group_id))

    @log_api_call
    def update_group(self, group_id: str, updates: dict):
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
    def update_all_expansion_state(self, is_expanded: bool):
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
    def get_load_order(self):
        """
        获取当前的加载顺序
        :param mods_config_file_path: ModsConfig.xml 文件路径
        :return: [package_id, package_id, ...]
        """
        try:
            res = self.load_order_mgr.read_active_mods()
            if not res or not res.get('active_mods', []):
                return ApiResponse.error("已启用的Mod为空，或文件读取失败!")
        except Exception as e:
            return ApiResponse.error(f"读取加载顺序文件出错: {e}")
        return ApiResponse.success({
            "file": self.load_order_mgr.mods_config_file,
            "active_ids": res.get('active_mods', []),
            "modify_time": res.get('modify_time', 0)
        })
    
    @log_api_call
    def open_load_order_file(self, mods_config_file_path: str|None = None):
        """
        打开 ModsConfig.xml 文件
        """
        file = ''
        # 默认路径为 ModsConfig.xml 所在目录
        if not mods_config_file_path:
            mods_config_file_path = self.load_order_mgr.config_dir
        # 检查路径是否合法，且是否为xml文件
        if os.path.isfile(mods_config_file_path) and (mods_config_file_path.endswith('.xml') or mods_config_file_path.endswith('.rws')):
            file = mods_config_file_path
        elif os.path.isdir(mods_config_file_path) :
            file = self.file_mgr.select_file_dialog(initial_dir=mods_config_file_path)
        else:
            file = self.file_mgr.select_file_dialog(initial_dir=self.load_order_mgr.config_dir)
        if not file:
            return ApiResponse.warning("未选择文件")
        res = self.load_order_mgr.read_active_mods(file)
        result = {
            "file": file,
            "active_ids": res.get('active_mods', []),
            "modify_time": res.get('modify_time', 0)
        }
        if not result["active_ids"]:
            return ApiResponse.error("解析文件出错!")
        return ApiResponse.success(result)
    
    @log_api_call
    def save_load_order(self, active_ids: List[str]):
        """
        保存当前激活列表到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        """
        try:
            success = self.load_order_mgr.save_active_mods(active_ids)
            if success: return ApiResponse.success()
            return ApiResponse.warning("取消保存")
        except Exception as e:
            return ApiResponse.error(f"保存 ModsConfig.xml 时出错: {e}")
    
    @log_api_call
    def export_load_order(self, active_ids: List[str], target_path: str|None = None, trigger_dialog: bool = True):
        """
        导出当前加载顺序到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        :param target_path: 导出路径
        """
        try:
            if not target_path and not trigger_dialog: trigger_dialog = True
            success = self.load_order_mgr.save_active_mods(active_ids, target_path, trigger_dialog)
            if success: return ApiResponse.success()
            return ApiResponse.warning("取消保存")
        except Exception as e:
            return ApiResponse.error(f"导出加载顺序时出错: {e}")

    @log_api_call
    def launch_game(self, profile_id: str):
        """启动游戏"""
        try:
            if not profile_id: profile_id = self.profile_mgr.current_profile.id
            if not profile_id: return ApiResponse.error("未指定 Profile ID")
            profile = self.profile_mgr.get_profile(profile_id)
            logger.debug(f"launch_game: profile_id={profile_id}, prefer_steam={settings.config.prefer_steam_launch}, steam_exe={settings.config.steam_exe_path}, is_steam={profile.is_steam}")
            # 检查 Steam 配置是否完整
            if(settings.config.prefer_steam_launch and settings.config.steam_exe_path and profile.is_steam):
                # 1. 获取当前 Profile 的启动参数（仅包含游戏相关参数）
                extra_args = self.profile_mgr.get_launch_args_only(profile_id)
                logger.debug(f"launch_game_steam: extra_args={extra_args}")
                # 2. 调用 Steam 管理器启动游戏
                self.steam_mgr.launch_via_steam_cmd(extra_args=extra_args)
            else:
                # 1. 获取当前 Profile 的启动参数
                launch_args = self.profile_mgr.get_launch_args(profile_id) 
                logger.debug(f"launch_game: launch_args={launch_args}")
                # 2. 调用游戏管理器启动游戏
                self.game_mgr.launch_game(custom_args=launch_args)
            
            # 3. 记录最后一次游玩时间到数据库
            self.profile_mgr.update_profile(profile_id, {
                "last_played_time": current_ms()
            })
            return ApiResponse.success(message="游戏启动成功，祝你游玩愉快！")
        except Exception as e:
            logger.error(f"Launch Game Error: {e}")
            return ApiResponse.error(f"启动游戏时出错: {e}")
    
    @log_api_call
    def get_game_info(self, install_path: str):
        """获取游戏信息"""
        if not install_path:
            return ApiResponse.error("未指定游戏安装路径")
        try:
            exe = self.game_mgr.detect_executable(install_path)
            version = self.game_mgr.get_game_version(install_path)
            is_steam = os.path.normpath(install_path).lower().rfind(os.path.join('steamlibrary', 'steamapps', 'common')) != -1
            if not exe :
                return ApiResponse.warning("无法获取游戏信息，请检查游戏安装路径是否正确！")
            return ApiResponse.success({
                "exe": exe,
                "version": version,
                "is_steam": is_steam,
            })
        except Exception as e:
            return ApiResponse.error(f"获取游戏信息时出错: {e}")

    # =========================================================================
    #  6. 文件与资源操作 (Files & Assets)
    # =========================================================================

    @log_api_call
    def open_path(self, path: str):
        try:
            self.file_mgr.open_in_explorer(path)
            logger.info(f"打开路径: {path}")
            return ApiResponse.success()
        except Exception as e:
            logger.error(f"打开路径时出错: {e}")
            return ApiResponse.error(f"打开路径时出错: {e}")
    
    @log_api_call
    def delete_path(self, path: str):
        """删除文件/文件夹"""
        try:
            success = self.file_mgr.delete_path(path)
            if success: return ApiResponse.success()
            return ApiResponse.warning("路径不存在或无法删除")
        except Exception as e:
            return ApiResponse.error(f"删除路径时出错: {e}")
    
    @log_api_call
    def delete_paths(self, paths: List[str]):
        """批量删除文件/文件夹"""
        try:
            success_count, error_list = self.file_mgr.delete_paths(paths)
            if success_count == len(paths):
                return ApiResponse.success()
            return ApiResponse.warning(f"成功删除 {success_count} 个路径，{len(error_list)} 个路径删除失败")
        except Exception as e:
            return ApiResponse.error(f"批量删除路径时出错: {e}")
    
    @log_api_call
    def get_all_backups(self):
        """获取所有备份文件路径"""
        try:
            backups = self.load_order_mgr.get_all_backups()
            return ApiResponse.success(backups)
        except Exception as e:
            return ApiResponse.error(f"获取备份文件时出错: {e}")
    
    @log_api_call
    def select_folder_dialog(self, initial_dir: str = ''):
        """
        打开系统原生的文件夹选择框
        """
        try:
            folder = self.file_mgr.select_folder_dialog(initial_dir)
            if folder:
                return ApiResponse.success(folder)
        except Exception as e:
            return ApiResponse.error(f"选择文件夹时出错: {e}")
        return ApiResponse.warning("未选择文件夹")
    
    @log_api_call
    def select_file_dialog(self, initial_dir: str = '', file_types = ('XML Files (*.xml;*.rws)', 'All Files (*.*)')):
        """
        打开系统原生的文件选择框
        """
        try:
            file = self.file_mgr.select_file_dialog(initial_dir, file_types)
            if file:
                return ApiResponse.success(file)
        except Exception as e:
            return ApiResponse.error(f"选择文件时出错: {e}")
        return ApiResponse.warning("未选择文件")

    @log_api_call
    def save_file_dialog(self, initial_dir: str = '', file_types = ('XML Files (*.xml;*.rws)', 'All Files (*.*)')):
        """
        打开系统原生的文件保存框
        """
        try:
            file = self.file_mgr.save_file_dialog(initial_dir, file_types)
            if file:
                return ApiResponse.success(file)
        except Exception as e:
            return ApiResponse.error(f"保存文件时出错: {e}")
        return ApiResponse.warning("未选择文件")
    
    @log_api_call
    def localize_workshop_mods(self, mod_ids: List[str]):
        """
        将工坊模组转为本地模组，并推送实时进度
        """
        cfg = settings.config
        local_root = cfg.local_mods_path
        
        # 1. 准备任务 (使用 JOIN 一次性查出所有需要的数据)
        # 这里的退回顺序逻辑直接在 Python 循环中处理，清晰易维护
        query = (ModAsset.select(ModAsset, UserModData.alias_name)
                .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                .where(ModAsset.package_id << [mid.lower() for mid in mod_ids], ModAsset.source == 'workshop') # type: ignore
                .dicts())
        try:
            # 2. 执行任务
            res = self.file_mgr.localize_workshop_mods(query, local_root, cfg.coexist_mod_folder_name_type)
            if not res: return ApiResponse.warning("没有可转换的工坊模组")
        except Exception as e:
            logger.error(f"Localize workshop mods failed: {e}", exc_info=True)
            return ApiResponse.error(f"本地化任务失败: {str(e)}")
        
        return ApiResponse.success(message="本地化任务已在后台启动")
    
    # =========================================================================
    #  7. 排序管理 (Sort Management)
    # =========================================================================

    @log_api_call
    def auto_sort_mods(self, active_ids: List[str]):
        """
        前端点击“自动排序”时调用
        """
        try:
            result = self.sorter.sort(active_ids)
            # result 包含: sorted_ids, auto_activated, warnings
            msg = "排序完成"
            if result.get('auto_activated'):
                msg += f" (自动激活了 {len(result['auto_activated'])} 个联锁项)"
            
            return ApiResponse.success(result, msg)
        except Exception as e:
            logger.error(f"Auto sort failed: {e}", exc_info=True)
            return ApiResponse.error(f"排序失败: {str(e)}")
        
    
    # =========================================================================
    #  9. 规则管理 (Rule Management)
    # =========================================================================

    @log_api_call
    def get_all_rules(self):
        """
        获取所有规则（用于规则管理界面显示）
        前端需要完整数据来支持搜索和查看
        """
        return ApiResponse.success({
            "community_rules": self.sorter.rule_mgr.community_rules, # 返回完整字典
            "community_rules_update_time": self.sorter.rule_mgr.community_rules_update_time,
            "user_mod_rules": self.sorter.rule_mgr.user_mod_rules,
            "user_dynamic_rules": self.sorter.rule_mgr.user_dynamic_rules,
            "settings": self.sorter.rule_mgr.settings,
        })

    @log_api_call
    def rule_update_user_mod(self, package_id: str, rule_content: dict):
        """保存单个规则"""
        try:
            success = self.sorter.rule_mgr.update_user_mod_rule(package_id, rule_content)
            return ApiResponse.success() if success else ApiResponse.error("保存失败")
        except Exception as e:
            return ApiResponse.error(f"保存失败: {str(e)}")
        
    @log_api_call
    def rule_delete_user_mod(self, package_id: str):
        """删除单个规则"""
        try:
            success = self.sorter.rule_mgr.delete_user_mod_rule(package_id)
            return ApiResponse.success() if success else ApiResponse.error("删除失败")
        except Exception as e:
            return ApiResponse.error(f"删除失败: {str(e)}")
    
    @log_api_call
    def rule_get_settings(self):
        """获取规则系统的全局设置 (开关状态、黑名单等)"""
        return ApiResponse.success(self.sorter.rule_mgr.settings)

    def change_rule_source_priority(self, rules_sources: List[str]):
        """
        改变规则来源的优先级
        rules_sources: 按优先级排序的规则来源列表
        """
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
        try:
            success = self.sorter.rule_mgr.set_global_setting(key, enabled)
            return ApiResponse.success() if success else ApiResponse.error("设置失败：无效的 Key")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def rule_toggle_community_mod(self, package_id: str, exclude: bool):
        """
        针对单个 Mod 禁用/启用社区规则提示 (黑名单操作)
        """
        try:
            success = self.sorter.rule_mgr.toggle_community_mod_exclusion(package_id, exclude)
            return ApiResponse.success() if success else ApiResponse.error("操作失败")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def rule_toggle_user_mod(self, package_id: str, exclude: bool):
        """
        针对单个 Mod 禁用/启用用户自定义单项规则 (黑名单操作)
        """
        try:
            success = self.sorter.rule_mgr.toggle_user_mod_rule_exclusion(package_id, exclude)
            return ApiResponse.success() if success else ApiResponse.error("操作失败")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def rule_toggle_dynamic(self, rule_id: str, enabled: bool):
        """切换动态规则的启用状态"""
        try:
            success = self.sorter.rule_mgr.toggle_dynamic_rule(rule_id, enabled)
            return ApiResponse.success() if success else ApiResponse.error("切换失败")
        except Exception as e:
            return ApiResponse.error(f"切换失败: {str(e)}")
    
    @log_api_call
    def rule_update_dynamic(self, rule_obj: dict):
        """保存动态规则"""
        try:
            success = self.sorter.rule_mgr.upsert_dynamic_rule(rule_obj)
            return ApiResponse.success() if success else ApiResponse.error("保存失败")
        except Exception as e:
            return ApiResponse.error(f"保存失败: {str(e)}")

    @log_api_call
    def rule_delete_dynamic(self, rule_id: str):
        """删除动态规则"""
        try:
            success = self.sorter.rule_mgr.delete_dynamic_rule(rule_id)
            return ApiResponse.success() if success else ApiResponse.error("删除失败")
        except Exception as e:
            return ApiResponse.error(f"删除失败: {str(e)}")

    @log_api_call
    def rule_update_community(self):
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

    @log_api_call
    def rule_export_bundle(self, dynamic_rule_ids: List[str], initial_dir: str = ''):
        """
        弹出对话框并导出
        file_types 在前端调用时也可以不传，这里给默认值
        """
        try:
            bundle = self.sorter.rule_mgr.create_export_bundle(dynamic_rule_ids)
            if not initial_dir: initial_dir = str(RULES_DIR)
            # 使用时间戳作为默认文件名
            default_name = f"RimOrder_Rules_{datetime.now().strftime('%Y%m%d')}.json"
            # 注意: file_types 参数格式需要符合 pywebview 的要求
            path = self.file_mgr.save_file_dialog(
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
        try:
            path = self.file_mgr.select_file_dialog(file_types=('JSON Files (*.json)',))
            if path:
                with open(path, 'r', encoding='utf-8') as f:
                    bundle = json.load(f)
                
                self.sorter.rule_mgr.process_import_bundle(bundle)
                return ApiResponse.success(message="规则包导入成功")
            return ApiResponse.warning("已取消")
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return ApiResponse.error(f"导入失败: {e}")
        
        
    # =========================================================================
    #  10. 日志管理 (Log Management)
    # =========================================================================

    @log_api_call
    def get_game_log_files(self):
        """ 获取游戏日志文件列表 """
        try:
            files = self.game_log_mgr.get_log_files()
            return ApiResponse.success(files)
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def read_game_log(self, filename: str):
        """ 读取并解析指定的游戏日志 """
        # 这是一个可能耗时的操作，@log_api_call 会帮我们记录耗时
        result = self.game_log_mgr.read_and_parse_log(filename)
        if 'error' in result:
            return ApiResponse.error(result['error'])
        return ApiResponse.success(result)
    
    @log_api_call
    def open_log_folder(self):
        """ 打开日志所在文件夹 """
        path = settings.config.user_data_path
        if path and os.path.exists(path):
            self.file_mgr.open_in_explorer(path)
            return ApiResponse.success()
        return ApiResponse.error("日志路径不存在")
    
    
    # =========================================================================
    #  11. 网络与下载管理 (Download Management)
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
            target_dir = os.path.join(os.getcwd(), "Downloads")
            os.makedirs(target_dir, exist_ok=True)
            
        task_id = self.download_mgr.add_task(url, target_dir, filename)
        return ApiResponse.success({"task_id": task_id}, "下载任务已添加")

    @log_api_call
    def cancel_download(self, task_id: str):
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
    #  更新管理 (Updates)
    # ==========================================
    @log_api_call
    def check_update(self, manual=True):
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
    def trigger_update_action(self):
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
    def ignore_version(self, version_str):
        """跳过当前版本"""
        settings.set('ignored_update_version', version_str)
        return ApiResponse.success()
    
    
    # =========================================================================
    #  12. Steam 集成 (Steam Integration)
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
            # 我们需要一个简单的方法来监控这些任务的完成
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

    @log_api_call
    def steam_subscribe(self, workshop_id: str):
        """调用 Steam 客户端订阅"""
        try:
            wid = int(workshop_id)
            success = self.steam_mgr.subscribe_item(wid)
            if success:
                return ApiResponse.success(message="已发送订阅请求 (需Steam运行中)")
            else:
                return ApiResponse.error("操作失败：SteamAPI 未就绪 (请确保Steam已运行)")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def steam_unsubscribe(self, workshop_id: str):
        """调用 Steam 客户端取消订阅"""
        try:
            wid = int(workshop_id)
            success = self.steam_mgr.unsubscribe_item(wid)
            if success:
                return ApiResponse.success(message="已发送取消订阅请求")
            else:
                return ApiResponse.error("操作失败：SteamAPI 未就绪")
        except Exception as e:
            return ApiResponse.error(str(e))
        
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
    #  13. AI 功能 (AI Features)
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
        获取模型列表 (替代原来的 ai_fetch_models)
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
            
        if not variables:
            variables = {}

        # 1. 生成唯一的任务 ID，供前端监听特定频道
        task_event_id = str(uuid.uuid4())

        # 2. 定义后台运行的工作线程
        def background_worker():
            # 为这个新线程创建一个全新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 运行我们写好的批量调度引擎
                results = loop.run_until_complete(
                    self.ai_mgr.execute_batch_task_async(task_key, items, variables, task_event_id)
                )
                # 任务彻底完成后，发送 complete 事件
                EventBus.emit(f'ai-batch-complete', {
                    'task_event_id': task_event_id,
                    'status': 'success', 
                    'data': results
                })
                # 可选：你可以直接在这里调用 ModDAO 批量入库
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
    #  用户配置环境管理 (Profiles)
    # ==========================================
    @log_api_call
    def get_profiles(self):
        '''获取所有环境配置'''
        return ApiResponse.success(self.profile_mgr.get_all_profiles())

    @log_api_call
    def get_current_profile(self):
        '''获取当前环境配置'''
        return ApiResponse.success(self.profile_mgr.get_current_profile())
    
    @log_api_call
    def create_profile(self, data: Dict[str, Any], copy_current_data: bool = False):
        try:
            self.profile_mgr.create_profile(data, copy_current_data)
            return ApiResponse.success(message="环境创建成功")
        except Exception as e:
            return ApiResponse.error(str(e))

    @log_api_call
    def update_profile(self, pid: str, data: Dict[str, Any]):
        try:
            self.profile_mgr.update_profile(pid, data)
            if pid == settings.config.current_profile_id:
                self.activate_profile(pid)
            return ApiResponse.success(message="配置已更新")
        except Exception as e:
            return ApiResponse.error(str(e))
        
    @log_api_call
    def delete_profile(self, pid):
        try:
            self.profile_mgr.delete_profile(pid)
            return ApiResponse.success(message="环境已删除")
        except Exception as e:
            return ApiResponse.error(str(e))
    
    @log_api_call
    def activate_profile(self, pid):
        """
        切换环境。
        前端调用此方法后，应该紧接着调用 get_initial_data 刷新界面。
        """
        if self.profile_mgr.activate_profile(pid):
            # 重要：刷新加载顺序管理器，使其指向新环境的配置文件
            self.load_order_mgr = LoadOrderManager() 
            # 切换成功后，前端通常会调用 get_initial_data 刷新全界面，所以这里只需返回成功
            res = {
                "profile": self.profile_mgr.get_current_profile().__dict__,
                "settings": asdict(settings.config)
            }
            return ApiResponse.success(message=f"已切换到环境: {pid}", data=res)
        return ApiResponse.error("切换失败，环境不存在")
    
    @log_api_call
    def scan_orphaned_profiles(self):
        """扫描可恢复的配置"""
        orphans = self.profile_mgr.scan_orphaned_profiles()
        return ApiResponse.success(orphans)

    @log_api_call
    def import_orphaned_profile(self, profile_data):
        """导入选定的配置"""
        success, msg = self.profile_mgr.import_profile_from_disk(profile_data)
        if success:
            return ApiResponse.success(message=msg)
        else:
            return ApiResponse.error(msg)
        
        
        
if __name__ == "__main__":
    valid_field_names = set(UserModData._meta.fields.keys()) # type: ignore
    print(valid_field_names)