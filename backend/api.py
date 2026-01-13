import os
from dataclasses import dataclass, asdict
from typing import Any

# 1. 引入配置管理
from backend.settings import settings

# 2. 引入数据库层
from backend.database.models import init_db
from backend.database.dao import ModDAO, GroupDAO

# 3. 引入业务逻辑管理器
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_mods_config import LoadOrderManager
from backend.managers.mgr_files import FileManager
from backend.scanner.parser_dlc import DLCParser
from backend.scanner.mod_scanner import ModScanner


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


class API:
    """
    暴露给 pywebview 前端的统一接口类。
    所有前端调用的 window.pywebview.api.xxx 方法都在这里定义。
    """

    def __init__(self):
        print("API Layer Initializing...")
        
        # 1. 初始化数据库
        # 数据库文件放在当前工作目录的data目录下
        db_path = os.path.join(os.getcwd(), 'data', 'mod_manager.db')
        self.is_first_db_init = not os.path.exists(db_path) # 标记是否首次初始化数据库
        init_db(db_path)
        
        # 2. 实例化各个管理器
        self.dlc_parser = None # 延迟初始化
        self.file_mgr = FileManager()    # 实例化 FileManager (它会自动启动 Server 线程)
        self.game_mgr = GameManager()
        self.load_order_mgr = LoadOrderManager() # 内部会自动从 settings 读取路径
        self.scanner = ModScanner()
        print("API Layer Ready.")


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
            "paths_configured": paths_valid,
            "settings": asdict(settings.config), # 转为字典发给前端
            "all_mods": all_mods,
            "groups": all_groups,
            "active_load_order": active_load_order,
            "is_first_db_init": self.is_first_db_init
        }
        self.is_first_db_init = False   # 标记数据库已初始化
        return ApiResponse.success(result)

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

    def auto_detect_paths(self, update_config=True):
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

    def save_setting(self, key, value):
        """保存单个设置项"""
        settings.set(key, value)
        # 如果修改的是路径，可能需要刷新管理器
        if 'path' in key:
            self.load_order_mgr = LoadOrderManager()
        return ApiResponse.success()

    def save_all_settings(self, settings_obj):
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

    def scan_mods(self, specific_paths=None, forced_update=False):
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

    def update_mod_user_data(self, package_id, data_dict):
        """
        即时保存用户对 Mod 的修改 (标签, 备注, 颜色等)
        """
        try:
            ModDAO.update_user_data(package_id, data_dict)
            return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(str(e))

    # =========================================================================
    #  4. 分组管理 (Groups) - 即时保存
    # =========================================================================

    def get_groups(self):
        return ApiResponse.success(GroupDAO.get_all_groups_structured())

    def create_group(self, name, color):
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

    def delete_group(self, group_id):
        return ApiResponse.success(GroupDAO.delete_group(group_id))

    def update_group(self, group_id, updates):
        """更新分组属性 (重命名、改色、折叠)"""
        # print(f"更新分组 {group_id} 为 {updates}")
        return ApiResponse.success(GroupDAO.update_group_info(group_id, **updates))

    def group_add_mods(self, group_id, mod_ids):
        """拖拽 Mod 进分组"""
        return ApiResponse.success(GroupDAO.add_mods_to_group(group_id, mod_ids))

    def group_remove_mods(self, group_id, mod_ids):
        """从分组移除 Mod"""
        return ApiResponse.success(GroupDAO.remove_mods_from_group(group_id, mod_ids))
    
    def update_all_expansion_state(self, is_expanded: bool):
        """一次性展开或折叠所有分组"""
        GroupDAO.update_all_expansion_state(is_expanded)
        return ApiResponse.success()

    def group_reorder(self, group_id_list):
        """分组排序"""
        return ApiResponse.success(GroupDAO.reorder_groups(group_id_list))

    def group_content_reorder(self, group_id, mod_id_list):
        """分组内 Mod 排序"""
        return ApiResponse.success(GroupDAO.reorder_mods_in_group(group_id, mod_id_list))

    # =========================================================================
    #  5. 加载顺序与游戏启动 (Load Order & Launch)
    # =========================================================================
    def get_load_order(self):
        """
        获取当前的加载顺序
        :param mods_config_file_path: ModsConfig.xml 文件路径
        :return: [package_id, package_id, ...]
        """
        try:
            active_ids = self.load_order_mgr.read_active_mods()
            if not active_ids:
                return ApiResponse.error("已启用的Mod为空，或文件读取失败!")
        except Exception as e:
            return ApiResponse.error(f"读取加载顺序文件出错: {e}")
        return ApiResponse.success({
            "file": self.load_order_mgr.mods_config_file,
            "active_ids": active_ids
        })
    
    def open_load_order_file(self, mods_config_file_path=None):
        """
        打开 ModsConfig.xml 文件
        """
        file = ''
        # 默认路径为 ModsConfig.xml 所在目录
        if not mods_config_file_path:
            mods_config_file_path = self.load_order_mgr.config_dir
        # 检查路径是否合法，且是否为xml文件
        if os.path.isfile(mods_config_file_path) and mods_config_file_path.endswith('.xml'):
            file = mods_config_file_path
        elif os.path.isdir(mods_config_file_path) :
            file = self.file_mgr.select_file_dialog(initial_dir=mods_config_file_path)
        else:
            file = self.file_mgr.select_file_dialog(initial_dir=self.load_order_mgr.config_dir)
        if not file:
            return ApiResponse.success("未选择文件")
        result = {
            "file": file,
            "active_ids": self.load_order_mgr.read_active_mods(file)
        }
        if not result["active_ids"]:
            return ApiResponse.error("解析文件出错!")
        return ApiResponse.success(result)
    
    
    def save_load_order(self, active_ids):
        """
        保存当前激活列表到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        """
        success = self.load_order_mgr.save_active_mods(active_ids)
        if success: return ApiResponse.success()
        return ApiResponse.error("保存 ModsConfig.xml 时出错!")
    
    def export_load_order(self, active_ids, target_path=None, trigger_dialog=True):
        """
        导出当前加载顺序到 ModsConfig.xml
        :param active_ids: 激活的 Mod 列表
        :param target_path: 导出路径
        """
        try:
            if not target_path and not trigger_dialog: trigger_dialog = True
            success = self.load_order_mgr.save_active_mods(active_ids, target_path, trigger_dialog)
            if success: return ApiResponse.success()
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

    def open_path(self, path):
        try:
            self.file_mgr.open_in_explorer(path)
            print(f"打开路径: {path}")
            return ApiResponse.success()
        except Exception as e:
            print(f"打开路径时出错: {e}")
            return ApiResponse.error(f"打开路径时出错: {e}")
    
    def delete_path(self, path):
        """删除文件/文件夹"""
        try:
            success = self.file_mgr.delete_path(path)
            if success:
                return ApiResponse.success()
        except Exception as e:
            return ApiResponse.error(f"删除路径时出错: {e}")
    
    def get_all_backups(self):
        """获取所有备份文件路径"""
        backups = self.load_order_mgr.get_all_backups()
        return ApiResponse.success(backups)
    
