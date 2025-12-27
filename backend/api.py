import os
from dataclasses import asdict
import webview # 引入 webview 库

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
        # 2. 获取所有 Mod 数据 (包含用户自定义数据)
        all_mods = ModDAO.get_all_mods_with_user_data()
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

        return {
            "status": "success",
            "paths_configured": paths_valid,
            "settings": asdict(settings.config), # 转为字典发给前端
            "all_mods": all_mods,
            "groups": all_groups,
            "active_load_order": active_load_order
        }

    # =========================================================================
    #  2. 设置与路径 (Settings & Paths)
    # =========================================================================

    def auto_detect_paths(self):
        """自动检测游戏路径"""
        result = self.game_mgr.auto_detect_paths()
        
        # 如果检测到了安装路径，自动更新设置
        if result.get('game_install_path'):
            settings.update_paths(result)
            # 重新初始化 LoadOrderManager (因为 Config 路径可能变了)
            self.load_order_mgr = LoadOrderManager()
            return {"status": "success", "paths": result}
        
        return {"status": "error", "message": "无法自动检测到游戏路径，请手动设置"}

    def save_setting(self, key, value):
        """保存单个设置项"""
        settings.set(key, value)
        # 如果修改的是路径，可能需要刷新管理器
        if 'path' in key:
            self.load_order_mgr = LoadOrderManager()
        return {"status": "success"}

    def save_all_settings(self, settings_obj):
        """保存所有设置 (前端设置面板保存时调用)"""
        # 批量更新
        for k, v in settings_obj.items():
            settings.set(k, v) # settings.set 内部会自动 save，这里可能稍微有点IO冗余，但安全
        
        # 刷新管理器
        self.load_order_mgr = LoadOrderManager()
        return {"status": "success"}

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
            return {"status": "error", "message": "没有配置有效的扫描路径"}

        # 调用异步扫描
        # 注意：这里不需要 try-catch 包裹整个逻辑，因为异常在线程内被捕获并通过事件发回了
        result = self.scanner.scan_paths_async(paths_to_scan, thumbnail_mgr=self.file_mgr, forced_update=forced_update)
        
        return {
            "status": "success", 
            "message": "Background scan started",
            "details": result
        }

    def update_mod_user_data(self, package_id, data_dict):
        """
        即时保存用户对 Mod 的修改 (标签, 备注, 颜色等)
        """
        try:
            ModDAO.update_user_data(package_id, data_dict)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # =========================================================================
    #  4. 分组管理 (Groups) - 即时保存
    # =========================================================================

    def get_groups(self):
        return GroupDAO.get_all_groups_structured()

    def create_group(self, name, color):
        try:
            # 后端生成 UUID 并入库
            new_group = GroupDAO.create_group(name, color)
            # 返回完整对象供前端渲染
            return {
                "status": "success",
                "group": {
                    "group_id": new_group.group_id,
                    "name": new_group.name,
                    "color": new_group.color,
                    "sort_index": new_group.sort_index,
                    "is_expanded": new_group.is_expanded,
                    "mod_ids": []
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_group(self, group_id):
        GroupDAO.delete_group(group_id)
        return {"status": "success"}

    def update_group(self, group_id, updates):
        """更新分组属性 (重命名、改色、折叠)"""
        GroupDAO.update_group_info(group_id, **updates)
        print(f"更新分组 {group_id} 为 {updates}")
        return {"status": "success"}

    def group_add_mods(self, group_id, mod_ids):
        """拖拽 Mod 进分组"""
        GroupDAO.add_mods_to_group(group_id, mod_ids)
        return {"status": "success"}

    def group_remove_mods(self, group_id, mod_ids):
        """从分组移除 Mod"""
        GroupDAO.remove_mods_from_group(group_id, mod_ids)
        return {"status": "success"}

    def group_reorder(self, group_id_list):
        """分组排序"""
        GroupDAO.reorder_groups(group_id_list)
        return {"status": "success"}

    def group_content_reorder(self, group_id, mod_id_list):
        """分组内 Mod 排序"""
        GroupDAO.reorder_mods_in_group(group_id, mod_id_list)
        return {"status": "success"}

    # =========================================================================
    #  5. 加载顺序与游戏启动 (Load Order & Launch)
    # =========================================================================
    def get_load_order(self, mods_config_file_path=None):
        """
        获取当前的加载顺序
        :param mods_config_file_path: ModsConfig.xml 文件路径
        :return: [package_id, package_id, ...]
        """
        active_ids = self.load_order_mgr.read_active_mods(mods_config_file_path)
        if not active_ids:
            return {"status": "error", "message": "Failed to read active mods"}
        return {"status": "success", "load_order": active_ids}
    
    def save_load_order(self, active_ids):
        """
        保存当前激活列表到 ModsConfig.xml
        """
        success = self.load_order_mgr.save_active_mods(active_ids)
        if success:
            return {"status": "success"}
        return {"status": "error", "message": "Failed to write ModsConfig.xml"}

    def launch_game(self):
        """启动游戏"""
        return self.game_mgr.launch_game()

    # =========================================================================
    #  6. 文件与资源操作 (Files & Assets)
    # =========================================================================

    def open_path(self, path):
        return self.file_mgr.open_in_explorer(path)
    
    def open_load_order_file(self, mods_config_file_path=None):
        """
        打开 ModsConfig.xml 文件
        """
        if not mods_config_file_path:
            mods_config_file_path = self.load_order_mgr.config_dir
        file = self.select_file_dialog(initial_dir=mods_config_file_path)
        if not file:
            return {"status": "error", "message": "未选择文件"}
        return self.get_load_order(file)
    
    
    def select_folder_dialog(self, initial_dir='', title="选择文件夹"):
        """
        打开系统原生的文件夹选择框
        """
        # 获取当前活动窗口
        if len(webview.windows) > 0:
            window = webview.windows[0]
            # 调用原生对话框
            # allow_multiple=False: 单选
            result = window.create_file_dialog(
                webview.FileDialog.FOLDER, 
                directory=initial_dir if initial_dir else '', 
                allow_multiple=False
            )
            # result 返回的是一个列表 (因为可能多选)，或者 None (取消)
            if result and len(result) > 0:
                return result[0]
        return None

    def select_file_dialog(self, initial_dir='', title="选择文件", file_types=('XML Files (*.xml)', 'All Files (*.*)')):
        """
        打开系统原生的文件选择框
        file_types 示例: ('XML Files (*.xml)', 'All Files (*.*)')
        """
        if len(webview.windows) > 0:
            window = webview.windows[0]
            result = window.create_file_dialog(
                webview.FileDialog.OPEN, 
                directory=initial_dir if initial_dir else '', 
                allow_multiple=False,
                file_types=file_types
            )
            if result and len(result) > 0:
                return result[0]
        return None