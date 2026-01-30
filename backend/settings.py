import json
import os
import shutil
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, List

# 配置文件路径
HOME_DIR = Path(os.getcwd())
CONFIG_DIR = HOME_DIR / "data"
CONFIG_FILE = CONFIG_DIR / "config.json"
# 定义缩略图缓存目录
CACHE_DIR = HOME_DIR / "cache" / "thumbnails"
# 规则文件存放路径
RULES_DIR = HOME_DIR / "data" / "rules"
USER_RULES_PATH = RULES_DIR / "user_rules.json"
COMMUNITY_RULES_PATH = RULES_DIR / "communityRules.json"
# 工具目录
TOOLS_DIR = HOME_DIR / "tools"

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



@dataclass
class SteamConfig:
    steamcmd_path: str = str(TOOLS_DIR / "steamcmd" / "steamcmd.exe")
    use_steam_client: bool = True  # 是否优先尝试使用 Steam 客户端
    steam_appid: int = 294100      # RimWorld AppID

@dataclass
class AppConfig:
    """
    配置数据结构定义。
    在这里定义字段和默认值，类型安全且清晰。
    """
    # --- 路径设置 ---
    game_install_path: str = ""
    game_data_path: str = ""  # RimWorld 数据文件夹 (Ludeon Studios...)
    game_config_path: str = ""  # RimWorld 配置文件夹 (Ludeon Studios...)
    workshop_mods_path: str = ""
    local_mods_path: str = ""
    home_path: str = str(Path(os.getcwd())) # 本程序路径
    community_rules_url: str = "https://github.com/RimSort/Community-Rules-Database/blob/main/communityRules.json"
    community_rules_path: str = str(COMMUNITY_RULES_PATH)
    user_rules_path: str = str(USER_RULES_PATH)
    
    # --- 游戏设置 ---
    game_version: str = ""
    
    # --- 界面设置 ---
    language: str = "ZH-cn"     # 默认语言
    theme: str = "system"       # light, dark, system
    window_width: int = 1400
    window_height: int = 900
    font_size: int = 14
    open_url_on_system: bool = False  # 是否在系统默认浏览器打开链接
    
    # --- 高级设置 ---
    backup_retention_days: int = 30  # 备份保留天数
    enable_auto_scan: bool = True    # 启动时自动扫描
    delete_missing_mods_data: bool = False    # 是否删除数据库中缺失的 Mod 数据
    
    # --- 缓存忽略列表 (示例) ---
    ignored_paths: list = field(default_factory=lambda: [".git", "__pycache__"])
    
    # --- 网络设置 ---
    network: NetworkConfig = field(default_factory=NetworkConfig)
    steam: SteamConfig = field(default_factory=SteamConfig)
    
    # --- 开发与调试设置 ---
    debug_mode: bool = True  # 开发模式开关
    log_retention_days: int = 7  # 日志保留天数
    log_level: str = "INFO"  # 默认日志等级 DEBUG, INFO, WARNING, ERROR
    

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
        self.config: AppConfig = self._load()
        self._initialized = True

    def _ensure_config_dir(self):
        """ 确保配置目录存在 """
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(parents=True)
        # 确保日志目录存在
        log_dir = Path(os.getcwd()) / "data" / "logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True)
            

    def _load(self) -> AppConfig:
        if not CONFIG_FILE.exists():
            return AppConfig()

        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 创建默认对象
            cfg = AppConfig()
            # 递归更新逻辑
            # 1. 更新顶层字段
            for k, v in data.items():
                if hasattr(cfg, k) and k != 'network':
                    setattr(cfg, k, v)
            # 2. 显式处理 network 嵌套
            if 'network' in data:
                net_data = data['network']
                # 处理 proxy
                if 'proxy' in net_data:
                    # 使用解包语法更新 ProxyConfig
                    # 注意过滤掉未知的字段，防止报错
                    valid_keys = ProxyConfig.__dataclass_fields__.keys()
                    clean_proxy_data = {k: v for k, v in net_data['proxy'].items() if k in valid_keys}
                    cfg.network.proxy = ProxyConfig(**clean_proxy_data)
                
                # 处理 hosts
                if 'hosts' in net_data:
                    cfg.network.hosts = net_data['hosts']

            return cfg

        except Exception as e:
            print(f"Config load error: {e}")
            return AppConfig()

    def save(self):
        """保存当前配置到磁盘"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
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
        支持: settings.set('language', 'en')
        """
        if hasattr(self.config, key):
            # 类型校验（可选，简单的做一下防止 int 变 str）
            target_type = type(getattr(self.config, key))
            if target_type != type(value) and target_type != str: # str比较宽松
                 # 尝试转换，或者打印警告
                 # value = target_type(value)
                 pass
            
            setattr(self.config, key, value)
            self.save()
        else:
            print(f"Warning: Attempted to set unknown setting key: {key}")

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
        p1 = self.config.game_install_path
        p2 = self.config.game_config_path
        
        if p1 and os.path.exists(p1) and p2 and os.path.exists(p2):
            return True
        return False

# 全局单例实例
settings = SettingsManager()