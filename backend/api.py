import os
import base64
import subprocess
from backend.database import DatabaseManager
from backend.scanner import ModScanner
from backend.detector import GameDetector
from backend.settings import SettingsManager
from backend.game_config import ConfigManager
from backend.server import AssetServer


# 这是一个 API 类，前端 JS 可以直接调用这里的方法
class API:
    def __init__(self):
        # 1. 加载设置
        self.settings = SettingsManager()
        # 2. 初始化数据库
        self.db = DatabaseManager()
        # 3. 初始化工具
        self.scanner = ModScanner()
        self.detector = GameDetector()
        self.asset_server = AssetServer() # 启动图片服务器
        print("后台服务已加载。数据库和扫描器已初始化。")
        
        # # 4. 如果是第一次运行或没有路径，尝试自动检测
        # if self.settings.get("first_run") or not self.settings.get("workshop_mods_path"):
        #     print("首次运行或路径缺失，尝试自动检测...")
        #     paths = self.detector.get_rimworld_paths()
        #     if paths:
        #         self.settings.update_paths(paths)
                
        # 5. 初始化配置管理器 (备份/读取核心文件)
        game_config_path = self.settings.get("game_config_path")
        self.config_mgr = None
        if game_config_path and os.path.exists(game_config_path):
            self.config_mgr = ConfigManager(game_config_path)
        
        # 6. 启动时的数据库维护
        self._startup_maintenance()
        
    def _startup_maintenance(self):
        """启动时维护：扫描Mod信息变化，清理旧Mod，同步Active列表"""
        # A. 扫描 Mod 信息变化
        self.scan_current_paths()
        # B. 清理已删除的 Mod
        # self.db.cleanup_removed_mods()
        # C. 可以在这里预加载一次 active 列表，但通常前端加载完毕后请求更好
        
    
    # --- 主要数据交互接口 ---
    def get_initial_data(self):
        """
        前端初始化时调用，一次性返回：
        1. 是否需要手动设置路径
        2. 当前数据库的所有 Mod
        3. 当前 ModsConfig.xml 中的启用列表 (Active List)
        """
        print("前端请求初始化数据……")
        # 1. 检查路径状态
        workshop_mods_path = self.settings.get("workshop_mods_path")
        local_mods_path = self.settings.get("local_mods_path")
        game_install_path = self.settings.get("game_install_path")
        game_config_path = self.settings.get("game_config_path")
        
        # 读取游戏版本号
        game_version = "未知版本"
        if game_install_path and os.path.exists(game_install_path):
            version_file = os.path.join(game_install_path, "Version.txt")
            if os.path.exists(version_file):
                with open(version_file, "r", encoding="utf-8") as f:
                    game_version = f.read().strip()
        self.settings.set("game_version", game_version)
        
        # 路径检查
        paths_valid = False
        if workshop_mods_path and os.path.exists(workshop_mods_path) \
        and local_mods_path and os.path.exists(local_mods_path) \
        and game_install_path and os.path.exists(game_install_path) \
        and game_config_path and os.path.exists(game_config_path):
            paths_valid = True
            
        # 2. 读取 Active List
        active_ids = []
        if self.config_mgr:
            active_ids = self.config_mgr.read_active_mods()
            
        # 3. 获取 DB 中所有 Mod
        all_mods = self.db.get_all_mods()
        
        return {
            "status": "success",
            "paths_configured": paths_valid,
            "settings": self.settings.config,
            "all_mods": all_mods,
            "active_load_order": active_ids, # 前端根据这个ID列表去 all_mods 里找对应数据
            "asset_server_port": self.asset_server.port # 传给前端的端口号
        }

    def auto_detect_paths(self):
        """前端调用：自动检测路径"""
        paths = self.detector.get_rimworld_paths()
        if paths:
            return {"status": "success", "paths": paths}
        return {"status": "error", "message": "无法自动找到 RimWorld 路径，请手动指定"}
    
    def scan_current_paths(self):
        """根据设置中的路径进行扫描，默认包含Workshop和本地模组路径"""
        paths = []
        p0 = self.settings.get("game_install_path")     # Data 目录-官方DLC
        p1 = self.settings.get("workshop_mods_path")    # Workshop 模组
        p2 = self.settings.get("local_mods_path")       # 本地模组
        if p0: paths.append(os.path.join(p0, "Data"))
        if p1: paths.append(p1)
        if p2: paths.append(p2)
        
        if not paths:
            return {"status": "error", "message": "未配置路径"}
            
        return self.scan_mods(paths)

    def scan_mods(self, path_list):
        """
        前端调用：扫描。
        path_list: 可以是一个路径字符串，也可以是路径列表 ['path1', 'path2']
        """
        print(f"Python 收到扫描请求，路径: {path_list}")
        
        if isinstance(path_list, str): path_list = [path_list]
        
        # 1. 获取数据库中现有的 Mod 时间戳，用于增量对比
        existing_mtimes = self.db.get_all_mods_mtimes()
        existing_paths = self.db.get_all_mods_path()
        all_new_mods = []
        all_missing_mods_ids = []
        
        # 2. 遍历所有路径，收集需要更新的 Mod 数据 (内存操作，快)
        for path in path_list:
            if os.path.exists(path):
                new_mods = self.scanner.scan_folder_for_batch(path, existing_mtimes)
                all_new_mods.extend(new_mods)
        
        # 检查是否有已删除的 Mod，有的话更新数据库
        for pkg_id, existing_path in existing_paths.items():
            if not os.path.exists(existing_path):
                all_missing_mods_ids.append(pkg_id)
                self.db.upsert_fields_by_id(pkg_id, {"path": ''})
                
        
        # 3. 批量写入数据库 (单次 I/O，极快)
        if all_new_mods:
            print(f"正在向数据库中更新 {len (all_new_mods)} 个模组……")
            self.db.save_mods_batch(all_new_mods)
        if all_missing_mods_ids:
            print(f"数据库中发现 {len(all_missing_mods_ids)} 个已删除模组……")
            
        if not ( all_new_mods or all_missing_mods_ids):
            print("未检测到任何变化。")
            
        # 4. 返回最新全量列表
        mods = self.db.get_all_mods()
        return {"status": "success", "count": len(mods), "mods": mods}
    
    def save_load_order(self, active_mod_ids):
        """前端点击应用：保存 Active 列表到 xml"""
        if not self.config_mgr:
            return {"status": "error", "message": "Config 路径未设置"}
            
        success = self.config_mgr.save_active_mods(active_mod_ids)
        if success:
            return {"status": "success", "message": "保存成功"}
        else:
            return {"status": "error", "message": "保存失败"}

    # --- 本地资源获取接口 ---
    def read_image(self, path):
        """读取本地图片并转换为 Base64 供前端显示"""
        if not path or not os.path.exists(path):
            return None
        
        try:
            with open(path, "rb") as f:
                # 读取二进制数据并转为 Base64 字符串
                encoded_string = base64.b64encode(f.read()).decode('utf-8')
                # 简单的扩展名判断
                ext = os.path.splitext(path)[1].lower()
                mime_type = "image/png" if ext == ".png" else "image/jpeg"
                # 返回完整的数据 URI
                return f"data:{mime_type};base64,{encoded_string}"
        except Exception as e:
            print(f"Error reading image {path}: {e}")
            return None
    
    # --- 设置相关接口 ---
    def get_setting(self, key):
        """前端调用：获取单个设置项"""
        return self.settings.get(key)
    
    def save_setting(self, key, value):
        """前端调用：设置单个设置项"""
        self.settings.set(key, value)
        if key == "game_config_path":
             if os.path.exists(value):
                self.config_mgr = ConfigManager(value)
        return {"status": "success"}

    def get_settings_dict(self):
        """前端获取所有设置的专用接口"""
        return self.settings.config
    
    def save_all_settings(self, settings_obj):
        """前端一次性保存所有设置"""
        for k, v in settings_obj.items():
            self.settings.set(k, v)
        # 如果路径变了，尝试重新加载 ConfigMgr
        if "game_config_path" in settings_obj:
            p = settings_obj["game_config_path"]
            if os.path.exists(p):
                self.config_mgr = ConfigManager(p)
        return {"status": "success"}
    
    # --- 外部程序调用接口 ---
    def launch_game(self):
        """启动 RimWorld"""
        install_path = str(self.settings.get("game_install_path"))
        if not install_path or not os.path.exists(install_path):
            return {"status": "error", "message": "游戏安装路径未设置"}
        
        # 尝试寻找可执行文件
        exes = ["RimWorldWin64.exe", "RimWorldWin.exe", "RimWorldLinux", "RimWorldMac"]
        target_exe = None
        for exe in exes:
            p = os.path.join(install_path, exe)
            if os.path.exists(p):
                target_exe = p
                break
        
        if target_exe:
            try:
                # 使用 subprocess.Popen 非阻塞启动
                subprocess.Popen([target_exe], cwd=install_path, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name=='nt' else 0)
                return {"status": "success", "message": f"游戏已启动:{os.path.basename(target_exe)}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": "在安装目录找不到可执行文件"}
    
    # -- 暂时没啥用的接口 ---

