# backend/settings.py

import json
import os
from dataclasses import dataclass, asdict, field, fields, is_dataclass
from pathlib import Path
import sys
from typing import Dict, Any, List


# 配置文件路径
HOME_DIR = Path(os.getcwd())
# 获取 exe 所在的真实目录
if getattr(sys, 'frozen', False):
    # PyInstaller 打包模式
    HOME_DIR = Path(sys.executable).parent
else:
    # 开发模式
    HOME_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = HOME_DIR / "data"                # 数据目录
CONFIG_PATH = DATA_DIR / "config.json"      # 配置文件路径
UPDATE_CACHE_DIR = HOME_DIR / "updates"     # 更新目录
TOOLS_DIR = HOME_DIR / "tools"                # 工具目录
MODS_DIR = HOME_DIR / "mods"                # 模组目录

# 定义缩略图缓存目录
CACHE_DIR = HOME_DIR / "cache" / "thumbnails"
# 规则存放路径
RULES_DIR = DATA_DIR / "rules"
USER_RULES_PATH = RULES_DIR / "user_rules.json"             # 用户规则路径
COMMUNITY_RULES_PATH = RULES_DIR / "communityRules.json"    # 社区库规则路径
# 外置数据库路径
COMMUNITY_WORKSHOP_DB_PATH = DATA_DIR / "steamDB.json"         # 社区库数据库路径
COMMUNITY_INSTEAD_DB_PATH = DATA_DIR / "replacements.json.gz"  # 替代Mod数据库路径


@dataclass
class ProxyConfig:
    enabled: bool = False
    # 代理类型: 'http' 或 'socks5'
    type: str = 'http' 
    host: str = ''
    port: int = 0
    username: str = ''
    password: str = ''
    # 排除列表 (不走代理的域名/IP)
    bypass_list: List[str] = field(default_factory=lambda: [
        "127.0.0.1", "localhost", "::1", 
    ])

@dataclass
class NetworkConfig:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    # 自定义 Hosts (域名 -> IP 映射)
    hosts: Dict[str, str] = field(default_factory=dict) 
    write_to_system_hosts: bool = False         # 是否将自定义 Hosts 写入系统 hosts 文件
    use_proxy_on_steamcmd: bool = False         # SteamCMD 是否使用代理
    use_proxy_on_ai: bool = False               # AI 是否使用代理

@dataclass
class AIConfig:
    enabled: bool = False
    api_type: str = "custom"  # 可选值: 'official' 或 'custom'
    provider: str = "openai"  # openai, anthropic, google
    base_url: str = "https://api.openai.com/v1"  # 允许自定义，如 DeepSeek, LocalAI
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7     # 温度参数（控制输出随机性）
    max_tokens: int = 5000       # 最大令牌数（限制模型输出长度）
    max_concurrency: int = 3     # 最大并发请求数（避免被API封锁）

@dataclass
class SteamConfig:
    steamcmd_path: str = str(TOOLS_DIR / "steamcmd" / "steamcmd.exe")
    use_steam_client: bool = True  # 是否优先尝试使用 Steam 客户端
    steam_appid: int = 294100      # RimWorld AppID

@dataclass
class UIConfig:
    theme: str = "system"       # light, dark, system
    font_size: int = 16
    drag_delay: int = 30            # 拖动判定延迟 (毫秒)
    tooltip_hover_time: int = 1000  # 鼠标悬停显示提示时间 (毫秒)
    show_mod_hover_panel: bool = True  # 是否显示 Mod 悬停面板
    double_click_active_mod: bool = True  # 是否双击启用/停用 Mod
    
    # 主界面布局配置
    main_layout: List[Dict[str, Any]] = field(default_factory=lambda: [
        { 'id': 'details', 'visible': True },
        { 'id': 'library', 'visible': True },
        { 'id': 'active', 'visible': True },
        { 'id': 'sidebar', 'visible': True },
    ])
    
    show_icons_cloud: bool = True  # 是否显示动态图标云
    
    # Mod 详情面板布局配置
    mod_details_layout: List[Dict[str, Any]] = field(default_factory=lambda: [
        { 'id': 'basic_info', 'visible': True }, # 包ID、作者、链接、路径
        { 'id': 'files_info', 'visible': True },
        { 'id': 'time_info', 'visible': True },
        { 'id': 'relations_info', 'visible': True },
        { 'id': 'user_info', 'visible': True }, # 标签、备注、分组
        { 'id': 'description', 'visible': True },
    ])

    show_dependency_graph: bool = True  # 是否显示依赖关系图
    show_list_index: bool = True  # 是否显示列表索引列
    show_list_icon: bool = True  # 是否显示 Mod 图标
    show_list_mod_icon: bool = True  # 是否显示 Mod 图标
    show_list_modtype_icon: bool = True  # 是否显示 Mod 类型图标
    
    show_group_index: bool = True  # 是否显示分组索引列
    show_group_icon: bool = True  # 是否显示分组图标
    

@dataclass
class AppConfig:
    """
    配置数据结构定义。
    在这里定义字段和默认值，类型安全且清晰。
    """
    # --- 路径设置 ---
    game_install_path: str = ""
    user_data_path: str = ""    # 用户数据文件夹
    game_config_path: str = ""  # RimWorld 配置文件夹
    game_saves_path: str = ""   # RimWorld 存档文件夹
    game_dlc_path: str = ""     # RimWorld DLC 文件夹
    local_mods_path: str = ""
    workshop_mods_path: str = ""
    steamcmd_mods_path: str = str(TOOLS_DIR / "steamcmd" / "steamapps" / "workshop" / "content" / "294100")
    use_workshop_mods: bool = True
    steam_path: str = ""
    home_path: str = str(Path(os.getcwd())) # 本程序路径
    mods_path: str = str(MODS_DIR)  # 本程序默认模组路径
    
    # --- 游戏设置 ---
    game_version: str = ""
    current_profile_id: str = "default"   # 当前激活的环境ID
    run_commands: List[str] = field(default_factory=list)
    prefer_steam_launch: bool = True         # 是否通过 Steam 启动游戏
    
    
    # --- 高级设置 ---
    backup_retention_days: int = 30           # 备份保留天数
    enable_auto_scan: bool = True             # 启动时自动扫描
    enable_file_size_scan: bool = True         # 扫描时是否检查文件大小
    delete_missing_mods_data: bool = True     # 是否删除数据库中缺失的 Mod 数据
    open_url_on_system: bool = False          # 是否在系统默认浏览器打开链接
    sort_mods_by: str = "name"                # 排序方式: name, id, alias
    auto_activate_dependencies: bool = False   # 是否在排序时自动激活依赖项
    coexist_mod_folder_name_type: str = "workshop_id" # 共存Mod生成方式: workshop_id, package_id, name, alias
    show_coexistence_message: bool = True      # 是否显示共存Mod提示
    check_language_support: bool = True        # 是否检查语言支持
    # --- 社区设置 ---
    community_workshop_db_url: str = "https://github.com/RimSort/Steam-Workshop-Database/blob/main/steamDB.json"
    community_workshop_db_path: str = str(COMMUNITY_WORKSHOP_DB_PATH)
    community_instead_db_url: str = "https://github.com/emipa606/UseThisInstead/blob/main/replacements.json.gz"
    community_instead_db_path: str = str(COMMUNITY_INSTEAD_DB_PATH)
    community_rules_url: str = "https://github.com/RimSort/Community-Rules-Database/blob/main/communityRules.json"
    community_rules_path: str = str(COMMUNITY_RULES_PATH)
    user_rules_path: str = str(USER_RULES_PATH)
    
    # --- 开发与调试设置 ---
    debug_mode: bool = False  # 开发模式开关
    log_retention_days: int = 7  # 日志保留天数
    log_level: str = "INFO"  # 默认日志等级 DEBUG, INFO, WARNING, ERROR
    enable_auto_update_check: bool = True  # 自动检查更新开关
    ignored_update_version: str = ""       # 跳过的版本号
    last_update_check_time: float = 0      # 上次检查时间（用于限流）
    
    # --- 界面设置 ---
    language: str = "ZH-cn"     # 默认语言
    window_width: int = 1400
    window_height: int = 900
    ui: UIConfig = field(default_factory=UIConfig)
    
    # --- 功能设置 ---
    network: NetworkConfig = field(default_factory=NetworkConfig)
    steam: SteamConfig = field(default_factory=SteamConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    

class SettingsManager:
    _instance = None
    
    def __new__(cls):
        """单例模式：确保全局只有一个 SettingsManager 实例"""
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._ensure_config_dir()
        self.config: AppConfig = self._load() # 加载配置
        self._initialized = True

    def _ensure_config_dir(self):
        """ 确保配置目录存在 """
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True)
        # 确保日志目录存在
        log_dir = Path(os.getcwd()) / "data" / "logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True)
            
    def _recursive_update(self, target_obj, source_dict: Dict[str, Any]):
        """
        递归更新 dataclass 对象。
        :param target_obj: 初始化的 dataclass 对象 (包含默认值)
        :param source_dict: 从 JSON 加载的字典
        """
        # 获取目标对象的所有字段定义
        target_fields = {f.name: f for f in fields(target_obj)}
        
        for key, value in source_dict.items():
            # 1. 忽略未知字段 (配置文件里有，但代码里没有定义的)
            if key not in target_fields:
                continue
            
            # 获取当前对象上的属性值
            current_attr = getattr(target_obj, key)
            
            # 2. 判断是否需要递归
            # 如果当前属性是 dataclass 实例，且来源值是字典，则递归更新
            if is_dataclass(current_attr) and isinstance(value, dict):
                self._recursive_update(current_attr, value)
            
            # 3. 普通赋值
            else:
                # 这里可以加一些简单的类型保护，比如防止把 str 赋给 int
                # 但 Python 鸭子类型通常允许直接赋值，除非为了极高的健壮性
                setattr(target_obj, key, value)
                # 4. 特殊处理：如果是 steamcmd_path，更新 steamcmd_mods_path
                if key == 'steamcmd_path':
                    settings.set('steamcmd_mods_path', str(Path(value) / "steamapps" / "workshop" / "content" / "294100"))
                

    def _load(self) -> AppConfig:
        """
        加载配置逻辑：
        1. 创建全默认值的 AppConfig 对象
        2. 读取 JSON
        3. 递归将 JSON 的值覆盖到 AppConfig 对象上
        """
        # 1. 如果文件不存在，直接返回全默认配置
        if not CONFIG_PATH.exists():
            return AppConfig()

        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 2. 实例化默认配置 (这里已经包含了所有定义的默认值)
            config = AppConfig()
            # 3. 递归更新 (核心逻辑)
            self._recursive_update(config, data)
            # 检查旧版配置位置
            legacy_game_data = data.get('network', {}).get('game_data_path')
            if not config.user_data_path and legacy_game_data:
                config.user_data_path = legacy_game_data
            return config

        except Exception as e:
            # 使用 logging.getLogger 避免循环导入
            print(f"Config load error: {e}")
            # 出错时返回默认配置，保证程序能跑
            return AppConfig()

    def save(self):
        """保存当前配置到磁盘"""
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                # asdict 将 dataclass 转换为字典
                json.dump(asdict(self.config), f, indent=4, ensure_ascii=False)
            # print("Settings saved.")
        except Exception as e:
            print(f"Error saving settings: {e}")

    # --- 便捷存取方法 ---

    def get(self, key: str) -> Any:
        """
        获取配置项。
        支持: settings.get('language')
        """
        if hasattr(self.config, key):
            return getattr(self.config, key)
        return None

    def set(self, key: str, value: Any):
        """
        设置配置项并自动保存。
        自动处理嵌套字典到 Dataclass 的转换，一劳永逸。
        """
        if not hasattr(self.config, key):
            print(f"Warning: Attempted to set unknown setting key: {key}")
            return

        current_attr = getattr(self.config, key)
        # 如果当前属性是一个 dataclass，且传入的值是个字典
        # 走递归更新，把字典里的值一个个填进对象里，而不是粗暴地覆盖对象
        if is_dataclass(current_attr) and isinstance(value, dict):
            self._recursive_update(current_attr, value)
        else:
            # 基础类型（str, int, bool, list）直接覆盖
            setattr(self.config, key, value)
            
        self.save()

    # 强烈建议新增这个方法供 api.save_all_settings 使用
    def update_from_dict(self, data_dict: Dict[str, Any]):
        """
        全量/批量更新配置项。
        前端传来的整坨 JSON dict，直接丢进这里，自动完成所有对象的嵌套解析。
        """
        if not isinstance(data_dict, dict):
            return
        self._recursive_update(self.config, data_dict)
        self.save()

    def update_paths(self, paths_dict: Dict[str, str]):
        """批量更新路径"""
        changed = False
        for k, v in paths_dict.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
                changed = True
        if changed:
            self.save()

    def validate_paths(self) -> bool:
        """检查核心路径是否配置且有效"""
        from backend.managers.mgr_game import GameManager
        p1 = GameManager.detect_executable(self.config.game_install_path)
        p2 = self.config.game_config_path
        
        if p1 and os.path.exists(p1) and p2 and os.path.exists(p2):
            return True
        return False

# 全局单例实例
settings = SettingsManager()