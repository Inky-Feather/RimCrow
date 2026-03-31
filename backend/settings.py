# backend/settings.py

import json
import os
from dataclasses import dataclass, asdict, field, fields, is_dataclass
from pathlib import Path
import sys
from typing import Dict, Any, List, Optional


# 1. 资源目录：存放前端文件、内置工具 (对应开发时的项目根目录)
if getattr(sys, 'frozen', False):
    # 打包后，指向临时解压目录
    BASE_RESOURCE_DIR = Path(getattr(sys, '_MEIPASS'))
else:
    # 开发时，指向当前文件所在目录的上一级（项目根目录）
    BASE_RESOURCE_DIR = Path(__file__).resolve().parent.parent

# 配置文件路径
HOME_DIR = Path(os.getcwd())
# 获取 exe 所在的真实目录
if getattr(sys, 'frozen', False):
    # PyInstaller 打包模式 时，指向 exe 所在目录
    HOME_DIR = Path(sys.executable).parent
else:
    # 开发模式, 指向当前文件所在目录的上一级（项目根目录）
    HOME_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = HOME_DIR / "data"                # 数据目录
CONFIG_PATH = DATA_DIR / "config.json"      # 配置文件路径
UPDATE_DIR = HOME_DIR / "updates"     # 更新目录
TOOLS_DIR = HOME_DIR / "tools"                # 工具目录
MODS_DIR = HOME_DIR / "mods"                # 模组目录
TOOL_MODS_DIR = HOME_DIR / "toolmods"    # 工具模组目录
CACHE_DIR = HOME_DIR / "cache"                # 缓存目录
BACKUP_DIR = HOME_DIR / "backups"                # 备份目录
# 定义缓存目录
GALLERY_CACHE_DIR = CACHE_DIR / "gallery"       # 定义画廊缓存目录
THUMBNAIL_CACHE_DIR = CACHE_DIR / "thumbnails"  # 定义缩略图缓存目录
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
    provider: str = "openai_compatible"  # openai, anthropic, google
    # OpenAI-compatible 的 endpoint 选择策略
    endpoint_mode: str = "auto"     # auto / chat_completions / responses
    base_url: str = "https://api.openai.com/v1"  # 允许自定义，如 DeepSeek, LocalAI
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    temperature: Optional[float] = 0.7     # 温度参数（控制输出随机性）允许“不传”
    max_tokens: int = 5000       # 最大令牌数（限制模型输出长度）
    max_concurrency: int = 3     # 最大并发请求数（避免被API封锁）

@dataclass
class UIConfig:
    theme: str = "system"       # light, dark, system
    font_size: int = 16
    drag_delay: int = 30            # 拖动判定延迟 (毫秒)
    detail_delay: int = 200         # Mod 详情页加载延迟 (毫秒)
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
    # game_install_path: str = ""    # RimWorld 安装路径
    # user_data_path: str = ""       # 用户数据文件夹
    # game_config_path: str = ""     # RimWorld 配置文件夹
    # game_saves_path: str = ""      # RimWorld 存档文件夹
    # game_dlc_path: str = ""        # RimWorld DLC 文件夹
    # local_mods_path: str = ""      # RimWorld 本地模组文件夹
    workshop_mods_path: str = ""   # RimWorld 公共工坊模组文件夹
    # use_workshop_mods: bool = True  # 是否使用公共工坊模组
    steam_path: str = ""          # Steam 安装路径
    home_path: str = str(HOME_DIR) # 本程序路径
    
    # steamcmd 下载路径
    steamcmd_path: str = str(TOOLS_DIR / "steamcmd")
    steamcmd_mods_path: str = str(TOOLS_DIR / "steamcmd" / "steamapps" / "workshop" / "content" / "294100")
    self_mods_path: str = str(MODS_DIR)  # 本程序默认模组路径
    # use_self_mods: bool = True          # 是否使用本程序模组
    move_old_self_mods: bool = False    # 修改路径后是否移动原有模组
    
    # --- 游戏设置 ---
    # game_version: str = ""               # RimWorld 版本
    current_profile_id: str = "default"   # 当前激活的环境ID
    # run_commands: List[str] = field(default_factory=list)   # 启动时运行的命令
    prefer_steam_launch: bool = True         # 是否通过 Steam 启动游戏
    enable_tool_mods: bool = False           # 是否启用 ToolMods 目录下的伴生模组
    use_raw_ids: bool = False               # 是否使用原始 Mod ID
    
    # --- 高级设置 ---
    backup_retention_days: int = 30           # 备份保留天数
    enable_auto_scan: bool = True             # 启动时自动扫描
    enable_file_size_scan: bool = True         # 扫描时是否检查文件大小
    delete_missing_mods_data: bool = False     # 是否删除数据库中缺失的 Mod 数据
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
    last_version: str = ""                 # 之前的版本号(用于判断是否更新过了)
    last_run_time: float = 0               # 上次运行时间（用于判断Mod是否存在变动）
    run_count: int = 0                     # 运行次数（用于判断是否需要重新扫描）
    
    # --- 界面设置 ---
    language: str = "ZH-cn"     # 默认语言
    window_width: int = 1400
    window_height: int = 900
    completed_guides: Dict[str, str] = field(default_factory=dict) # 存储已完成的引导, e.g. {"main_v1.0": "done"}
    ui: UIConfig = field(default_factory=UIConfig)
    
    # --- 功能设置 ---
    network: NetworkConfig = field(default_factory=NetworkConfig)
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
        if self._initialized: return
        self._ensure_config_dir()
        # self.config: AppConfig = self._load() # 加载配置
        
        # 1. 先初始化一个空的配置对象，防止加载过程中访问 self.config 崩溃
        self.config = AppConfig()
        # 2. 执行加载（此时 _recursive_update 访问 self.config 就安全了）
        self._load_to_config()
        
        self._initialized = True

    def _ensure_config_dir(self):
        """ 确保配置目录存在 """
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True)
        # 确保日志目录存在
        log_dir = DATA_DIR / "logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True)
        if not TOOL_MODS_DIR.exists():
            TOOL_MODS_DIR.mkdir(parents=True)
            
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
            if key not in target_fields: continue
            # 获取当前对象上的属性值
            current_attr = getattr(target_obj, key)
            # 2. 判断是否需要递归
            # 如果当前属性是 dataclass 实例，且来源值是字典，则递归更新
            if is_dataclass(current_attr) and isinstance(value, dict):
                self._recursive_update(current_attr, value)
            # 3. 普通赋值
            else:
                # 这里可以加一些简单的类型保护，比如防止把 str 赋给 int，但 Python 鸭子类型通常允许直接赋值，除非为了极高的健壮性
                setattr(target_obj, key, value)
                

    def _load_to_config(self):
        """
        将磁盘配置加载到现有的 self.config 中
        """
        if not CONFIG_PATH.exists(): return
        try:
            # 使用 utf-8-sig 兼容带 BOM 的文件，使用 errors='replace' 防止崩溃
            with open(CONFIG_PATH, 'r', encoding='utf-8-sig', errors='replace') as f:
                content = f.read()
                # 尝试修复损坏的 JSON (比如末尾被截断)
                from json_repair import repair_json
                data = repair_json(content, return_objects=True)
                
            if isinstance(data, dict):
                # 使用递归更新现有的 self.config
                self._recursive_update(self.config, data)
                # 加载完成后，手动同步一次衍生路径
                self._sync_derived_paths()
            
        except Exception as e:
            print(f"Config load error: {e}")
    
    def _sync_derived_paths(self):
        """
        统一管理所有依赖路径的计算逻辑。
        """
        # 根据 steamcmd_path 计算 steamcmd_mods_path
        if self.config.steamcmd_path:
            base_path = Path(self.config.steamcmd_path).resolve()
            new_path = str(base_path / "steamapps" / "workshop" / "content" / "294100")
            self.config.steamcmd_mods_path = new_path
            
    def get_default_community_paths(self):
        """获取默认的社区路径"""
        default_paths = {
            # "self_mods_path": str(),
            "steamcmd_mods_path": str(TOOLS_DIR / "steamcmd"),
            "community_workshop_db_path": str(COMMUNITY_WORKSHOP_DB_PATH),
            "community_instead_db_path": str(COMMUNITY_INSTEAD_DB_PATH),
            "community_rules_path": str(COMMUNITY_RULES_PATH),
            "user_rules_path": str(USER_RULES_PATH),
        }
        return default_paths
        
    
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
        设置配置项并自动处理路径同步逻辑
        """
        if not hasattr(self.config, key):
            print(f"Warning: Unknown key {key}")
            return
        # 记录关键路径的旧值用于比对
        old_self_mods_path = self.config.self_mods_path
        old_steamcmd_path = self.config.steamcmd_path
        current_attr = getattr(self.config, key)
        if is_dataclass(current_attr) and isinstance(value, dict):
            self._recursive_update(current_attr, value)
        else:
            setattr(self.config, key, value)
        # --- 逻辑触发区 ---
        # 1. 重新计算衍生路径
        self._sync_derived_paths()
        # 2. 如果 self_mods_path 变了，触发同步
        if key == 'self_mods_path' and old_self_mods_path != value:
            from backend.managers.mgr_files import FileManager
            FileManager.sync_steamcmd_root_link(
                old_mods_path=old_self_mods_path,
                move_old_data=self.config.move_old_self_mods
            )
        # 3. 如果 steamcmd_path 变了，也触发同步
        if old_steamcmd_path != self.config.steamcmd_path:
            from backend.managers.mgr_files import FileManager
            FileManager.sync_steamcmd_root_link()
        self.save()

    def save(self):
        """保存当前配置到磁盘"""
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                # asdict 将 dataclass 转换为字典
                json.dump(asdict(self.config), f, indent=4, ensure_ascii=False)
            # print("Settings saved.")
        except Exception as e:
            print(f"Error saving settings: {e}")

    # 强烈建议新增这个方法供 api.save_all_settings 使用
    def update_from_dict(self, data_dict: Dict[str, Any]):
        """
        全量更新，同样需要处理逻辑触发
        """
        old_self_mods_path = self.config.self_mods_path
        old_steamcmd_path = self.config.steamcmd_path
        self._recursive_update(self.config, data_dict)
        self._sync_derived_paths()
        # 检查并同步
        if old_self_mods_path != self.config.self_mods_path or \
           old_steamcmd_path != self.config.steamcmd_path:
            from backend.managers.mgr_files import FileManager
            FileManager.sync_steamcmd_root_link(
                old_mods_path=old_self_mods_path,
                move_old_data=self.config.move_old_self_mods
            )
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

# 全局单例实例
settings = SettingsManager()