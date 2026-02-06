from datetime import datetime
import json
import os
import threading
import time
import functools
import shutil
import webview
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
from send2trash import send2trash

# 1. 引入配置管理
from backend.settings import settings, RULES_DIR
from backend.utils.logger import logger
from backend._version import __version__, __build__

# 2. 引入数据库层
from backend.database.models import Mod, init_db
from backend.database.dao import ModDAO, GroupDAO

# 3. 引入业务逻辑管理器
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_mods_config import LoadOrderManager
from backend.managers.mgr_files import FileManager
from backend.scanner.parser_dlc import DLCParser
from backend.scanner.mod_scanner import ModScanner
from backend.managers.mgr_game_logs import GameLogManager
from backend.managers.mgr_sorter import OrderSorter
from backend.managers.mgr_network import NetworkManager
from backend.managers.mgr_download import DownloadManager
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_sub_browser import SubBrowserManager
from backend.managers.mgr_ai import AIManager
from backend.managers.mgr_update import UpdateManager, UpdateInfo


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
        return asdict(cls(status="success", data=data, message=message))

    @classmethod
    def error(cls, message, data=None):
        return asdict(cls(status="error", message=message, data=data))
    
    @classmethod
    def warning(cls, message, data=None):
        return asdict(cls(status="warning", message=message, data=data))



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
        
        # 2. 实例化各个管理器
        self.dlc_parser = None # 延迟初始化
        self.file_mgr = FileManager()    # 实例化 FileManager (它会自动启动 Server 线程)
        self.game_mgr = GameManager()
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
        if not self.dlc_parser and settings.config.game_install_path:
            data_dir = os.path.join(settings.config.game_install_path, 'Data')
            if os.path.exists(data_dir):
                # 这里初始化会自动处理全量缓存和增量更新
                self.dlc_parser = DLCParser(data_dir)

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
            # 简单的非空检查兜底
            paths_valid = os.path.exists(settings.config.game_install_path)
        self._ensure_dlc_parser()   # 确保 DLC Parser 初始化
        # 0. 获取游戏版本号
        game_version = self.game_mgr.get_game_version() if self.game_mgr else ""
        settings.config.game_version = game_version
        # 2. 获取所有 Mod 数据 (包含用户自定义数据), 并排除缺失的 Mod
        all_mods = ModDAO.get_all_mods_with_user_data(ignore_missing=True)
        # 3. 获取所有分组数据 (结构化)
        all_groups = GroupDAO.get_all_groups_structured()
        # 4. 获取当前激活的加载顺序
        active_load_order = self.load_order_mgr.read_active_mods()
        
        # DLC动态翻译注入
        for mod in all_mods:
            if self.dlc_parser:
                # 传入当前语言，Parser 内部会查找缓存
                self.dlc_parser.translate_record(mod, settings.config.language)

        # 【关键】在这里注入图片 URL
        for mod in all_mods:
            pkg_id = mod['package_id']
            icon_path = mod['icon_path']
            preview_path = mod['preview_path']
            
            # 1. 尝试获取已生成的缩略图路径 (物理路径)
            thumb_path = self.file_mgr.get_thumbnail_path(pkg_id)
            
            # 2. 决定列表图标 (优先用缩略图，没有则用原图)
            list_thumb_path = thumb_path if thumb_path else preview_path
            
            # 3. 转换为 HTTP URL
            if list_thumb_path:
                mod['thumb_url'] = self.file_mgr.get_asset_url(list_thumb_path)
            else:
                # 前端处理默认图，或者返回特定的 assets 路径
                mod['thumb_url'] = None 
            
            # 4. 详情页大图 URL
            if preview_path:
                mod['preview_url'] = self.file_mgr.get_asset_url(preview_path)
            else:
                mod['preview_url'] = None
            
            # 5. 图标 URL
            if icon_path:
                mod['icon_url'] = self.file_mgr.get_asset_url(icon_path)
            else:
                mod['icon_url'] = None 
                
        result = {
            "app_version": __version__,
            "build_mode": __build__,
            "paths_configured": paths_valid,
            "settings": asdict(settings.config), # 转为字典发给前端
            "all_mods": all_mods,
            "groups": all_groups,
            "active_load_order": active_load_order.get('active_mods', []),
            "active_load_modify_time": active_load_order.get('modify_time', 0),
            "is_first_db_init": self.is_first_db_init
        }
        if(paths_valid and all_mods): self.is_first_db_init = False   # 标记数据库已初始化
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
        
        # 如果检测到了安装路径，自动更新设置
        if result.get('game_install_path'):
            if update_config:   # 仅当请求时更新配置
                settings.update_paths(result)
                # 重新初始化 LoadOrderManager (因为 Config 路径可能变了)
                self.load_order_mgr = LoadOrderManager()
            return ApiResponse.success({"paths": result})
        
        return ApiResponse.error("无法自动检测到游戏路径，请手动设置！")

    def save_setting(self, key: str, value: Any):
        """保存单个设置项"""
        settings.set(key, value)
        # 如果修改的是路径，可能需要刷新管理器
        if 'path' in key:
            self.load_order_mgr = LoadOrderManager()
        return ApiResponse.success()

    def save_all_settings(self, settings_obj: dict):
        """保存所有设置 (前端设置面板保存时调用)"""
        # 批量更新
        for k, v in settings_obj.items():
            settings.set(k, v) # settings.set 内部会自动 save，这里可能稍微有点IO冗余，但安全
        # 刷新管理器
        self.load_order_mgr = LoadOrderManager()
        return ApiResponse.success()
    

    # =========================================================================
    #  3. Mod 扫描与管理 (Scanning & Mods)
    # =========================================================================
    @log_api_call
    def scan_mods(self, specific_paths: List[str]|None = None, forced_update: bool = False):
        """
        触发后台模组扫描。
        立即返回状态，前端通过监听 'scan-progress' 和 'scan-complete' 事件获取更新。
        :param specific_paths: 可选，指定要扫描的路径列表。如果为空，则使用设置中的默认路径。
        :param forced_update: 可选，是否强制更新所有 Mod 的数据。默认 False。
        """
        paths_to_scan = []
        if specific_paths:
            paths_to_scan = specific_paths
        else:
            # 默认扫描策略：DLC + Local + Workshop
            cfg = settings.config
            # 1. DLC (Data 目录)
            if cfg.game_install_path and os.path.exists(cfg.game_install_path):
                data_dir = os.path.join(cfg.game_install_path, 'Data')
                if os.path.exists(data_dir):
                    paths_to_scan.append(data_dir)
            # 2. Local Mods
            if cfg.local_mods_path and os.path.exists(cfg.local_mods_path):
                paths_to_scan.append(cfg.local_mods_path)
            # 3. Workshop Mods
            if cfg.workshop_mods_path and os.path.exists(cfg.workshop_mods_path):
                paths_to_scan.append(cfg.workshop_mods_path)
        if not paths_to_scan:
            return ApiResponse.error("没有配置有效的扫描路径")
        # 调用异步扫描
        # 注意：这里不需要 try-catch 包裹整个逻辑，因为异常在线程内被捕获并通过事件发回了
        result = self.scanner.scan_paths_async(paths_to_scan, thumbnail_mgr=self.file_mgr, forced_update=forced_update)
        return ApiResponse.success({ "details": result },"后台扫描已启动")
    
    @log_api_call
    def update_mod_time(self, mods_data_list: List[Dict[str, Any]]):
        """
        更新指定 Mod 列表 的 最后操作时间
        """
        try:
            # 净化数据只保留必要字段
            valid_fields = ['package_id', 'last_active_time', 'last_moved_time']
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
            for op in operations:
                action = op.get('action')
                target_path = op.get('target_path')
                
                if not target_path or not os.path.exists(target_path):
                    results.append({'path': target_path, 'status': 'error', 'msg': '路径不存在'})
                    continue

                if action == 'disable':
                    # 方案：重命名 About.xml -> About.xml.disabled
                    about_xml = os.path.join(target_path, 'About', 'About.xml')
                    disabled_xml = os.path.join(target_path, 'About', 'About.xml.disabled')
                    
                    if os.path.exists(about_xml):
                        try:
                            # 如果目标已存在，先删除旧的disabled (极其罕见)
                            if os.path.exists(disabled_xml):
                                os.remove(disabled_xml)
                            os.rename(about_xml, disabled_xml)
                            
                            # 尝试更新 shadow_paths，如果失败（Mod不存在）则忽略
                            # 因为下次扫描时，保留的 Mod 会入库。
                            keep_id = op.get('keep_id')
                            if keep_id:
                                self._add_shadow_path(keep_id, target_path)
                                
                            results.append({'path': target_path, 'status': 'success'})
                        except Exception as e:
                            results.append({'path': target_path, 'status': 'error', 'msg': str(e)})
                    else:
                        results.append({'path': target_path, 'status': 'skipped', 'msg': 'About.xml not found'})

                elif action == 'delete':
                    # 方案：移入回收站
                    try:
                        send2trash(os.path.abspath(target_path))
                        results.append({'path': target_path, 'status': 'success'})
                    except Exception as e:
                        results.append({'path': target_path, 'status': 'error', 'msg': str(e)})

            return ApiResponse.success(results, "冲突处理完成")
        except Exception as e:
            return ApiResponse.error(f"处理出错: {str(e)}")
    
    def _add_shadow_path(self, package_id: str, path: str):
        """辅助方法：更新 Mod 的 shadow_paths 字段"""
        try:
            mod = Mod.get_or_none(Mod.package_id == package_id)
            if mod:
                # 获取现有列表 (peewee JSON field 自动反序列化)
                current_paths = mod.shadow_paths or []
                if path not in current_paths:
                    current_paths.append(path)
                    mod.shadow_paths = current_paths
                    mod.save()
        except Exception as e:
            print(f"Error updating shadow paths: {e}")
    
    # =========================================================================
    #  4. 分组管理 (Groups) - 即时保存
    # =========================================================================

    def get_groups(self):
        return ApiResponse.success(GroupDAO.get_all_groups_structured())

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

    def delete_group(self, group_id: str):
        return ApiResponse.success(GroupDAO.delete_group(group_id))

    def update_group(self, group_id: str, updates: dict):
        """更新分组属性 (重命名、改色、折叠)"""
        # print(f"更新分组 {group_id} 为 {updates}")
        return ApiResponse.success(GroupDAO.update_group_info(group_id, **updates))

    def group_add_mods(self, group_id: str, mod_ids: List[str]):
        """拖拽 Mod 进分组"""
        return ApiResponse.success(GroupDAO.add_mods_to_group(group_id, mod_ids))

    def group_remove_mods(self, group_id: str, mod_ids: List[str]):
        """从分组移除 Mod"""
        return ApiResponse.success(GroupDAO.remove_mods_from_group(group_id, mod_ids))
    
    def update_all_expansion_state(self, is_expanded: bool):
        """一次性展开或折叠所有分组"""
        GroupDAO.update_all_expansion_state(is_expanded)
        return ApiResponse.success()

    def group_reorder(self, group_id_list: List[str]):
        """分组排序"""
        return ApiResponse.success(GroupDAO.reorder_groups(group_id_list))

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

    def launch_game(self):
        """启动游戏"""
        try:
            self.game_mgr.launch_game()
        except Exception as e:
            return ApiResponse.error(f"启动游戏时出错: {e}")
        return ApiResponse.success()

    # =========================================================================
    #  6. 文件与资源操作 (Files & Assets)
    # =========================================================================

    def open_path(self, path: str):
        try:
            self.file_mgr.open_in_explorer(path)
            print(f"打开路径: {path}")
            return ApiResponse.success()
        except Exception as e:
            print(f"打开路径时出错: {e}")
            return ApiResponse.error(f"打开路径时出错: {e}")
    
    def delete_path(self, path: str):
        """删除文件/文件夹"""
        try:
            success = self.file_mgr.delete_path(path)
            if success:
                return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(f"删除路径时出错: {e}")
    
    def get_all_backups(self):
        """获取所有备份文件路径"""
        try:
            backups = self.load_order_mgr.get_all_backups()
            return ApiResponse.success(backups)
        except Exception as e:
            return ApiResponse.error(f"获取备份文件时出错: {e}")
    
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
        return ApiResponse.error("未选择文件夹")
    
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
        return ApiResponse.error("未选择文件")

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
        return ApiResponse.error("未选择文件")
    
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
        
    @log_api_call
    def check_load_order_health(self, active_ids: List[str]):
        """
        常态化健康检查：检测当前顺序是否违反 About.xml、社区规则或用户规则
        前端通常在拖拽停止后调用
        """
        try:
            issues = self.sorter.check_health(active_ids)
            # 返回的是 List[dict]，每个 dict 包含 mod_id, type, level, message, source
            return ApiResponse.success(issues)
        except Exception as e:
            return ApiResponse.error(f"健康检查失败: {str(e)}")
        
    
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
        更新社区规则库 (同步阻塞模式)
        """
        try:
            file_folder: str = os.path.dirname(settings.config.community_rules_path)
            file_name: str = os.path.basename(settings.config.community_rules_path)
            url = settings.config.community_rules_url
            if not os.path.exists(file_folder):
                os.makedirs(file_folder)
            # print(f"Downloading community rules to: {file_folder}\\{file_name}\nfrom: {url}")
            # 2. 添加任务 (复用 DownloadManager，这样前端状态栏会有进度条！)
            task_id = self.download_mgr.add_task(url, file_folder, file_name)
            # 3. 【关键】阻塞等待下载完成 (最长等待 60秒)
            logger.info(f"Waiting for community rules download... task_id={task_id}")
            success = self.download_mgr.wait_for_task(task_id, timeout=60)
            if not success:
                # 检查是超时还是下载报错
                task = self.download_mgr.tasks.get(task_id)
                error_msg = task.error_msg if task else "Timeout"
                return ApiResponse.error(f"下载失败: {error_msg}")
            # 4. 【关键】下载完成后，通知 RuleManager 重新加载磁盘文件
            self.sorter.rule_mgr.load_all() 

            return ApiResponse.success(message="社区规则库更新完成")
            
        except Exception as e:
            logger.error(f"Update community rules failed: {e}")
            return ApiResponse.error(str(e))

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
        path = settings.config.game_data_path
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

    def cancel_download(self, task_id: str):
        self.download_mgr.cancel_task(task_id)
        return ApiResponse.success(message="尝试取消任务")

    def get_active_downloads(self):
        """获取所有任务状态 (用于 UI 恢复)"""
        return ApiResponse.success(self.download_mgr.get_tasks_info())
    
    def open_sub_browser(self, url='', title = 'RimModManager'):
        """打开或更新 浏览器子窗口"""
        if not self.browser_window: 
            self.browser_window = SubBrowserManager(self)
        self.browser_window.open(url, title)

    
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
    def ai_fetch_models(self, temp_config: dict):
        """
        获取模型列表 (用于配置页面的下拉菜单)
        :param temp_config: 前端表单中的临时配置 {provider, base_url, api_key}
        """
        try:
            models = self.ai_mgr.fetch_available_models(temp_config)
            return ApiResponse.success(models)
        except Exception as e:
            return ApiResponse.error(f"连接失败: {str(e)}")

    @log_api_call
    def ai_chat(self, message: str, config_data: dict):
        """简单的自由对话"""
        try:
            # 使用 'chat' 模板
            result = self.ai_mgr.execute_task('chat', {'message': message})
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
    
    
    # ==========================================
    #  更新管理 (Updates)
    # ==========================================
    def check_update(self, manual=True):
        """
        检查版本更新
        :param manual: 是否为用户手动触发（手动触发不检查跳过版本）
        """
        try:
            info = self.update_mgr.check_all()
            # 如果是非手动检查，且版本是被跳过的，则返回无更新
            if not manual and info.version == settings.config.ignored_update_version:
                return ApiResponse.success({ "has_update": False })
            settings.set('last_update_check_time', time.time())
            # 将 dataclass 转为字典传给前端
            return ApiResponse.success(asdict(info))
        except Exception as e:
            return ApiResponse.error(f"检查更新失败: {str(e)}")

    def install_update(self, temp_exe_path):
        """
        启动热更新脚本并关闭主程序
        :param temp_exe_path: 已经下载好的新版本临时文件路径
        """
        try:
            if not os.path.exists(temp_exe_path):
                return ApiResponse.error("更新包文件不存在")
            
            # 调用管理器执行热交换
            self.update_mgr.execute_hot_swap(temp_exe_path)
            return ApiResponse.success(message="更新脚本已启动")
        except Exception as e:
            return ApiResponse.error(str(e))

    def ignore_version(self, version_str):
        """跳过当前版本"""
        settings.set('ignored_update_version', version_str)
        return ApiResponse.success()