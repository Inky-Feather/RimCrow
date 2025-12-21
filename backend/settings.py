import json
import os
import shutil
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any

# 配置文件路径
CONFIG_DIR = Path(os.getcwd()) / "data"
CONFIG_FILE = CONFIG_DIR / "config.json"

@dataclass
class AppConfig:
    """
    配置数据结构定义。
    在这里定义字段和默认值，类型安全且清晰。
    """
    # --- 路径设置 ---
    game_install_path: str = ""
    game_config_path: str = ""  # RimWorld 配置文件夹 (Ludeon Studios...)
    workshop_mods_path: str = ""
    local_mods_path: str = ""
    
    # --- 游戏设置 ---
    game_version: str = ""
    
    # --- 界面设置 ---
    language: str = "ZH-cn"     # 默认语言
    theme: str = "system"       # light, dark, system
    window_width: int = 1400
    window_height: int = 900
    font_size: int = 14
    
    # --- 高级设置 ---
    backup_retention_days: int = 30  # 备份保留天数
    enable_auto_scan: bool = True    # 启动时自动扫描
    delete_missing_mods_data: bool = False    # 是否删除数据库中缺失的 Mod 数据
    
    # --- 缓存忽略列表 (示例) ---
    ignored_paths: list = field(default_factory=lambda: [".git", "__pycache__"])

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

    def _load(self) -> AppConfig:
        """加载配置，并处理旧配置文件缺少新字段的情况"""
        # 1. 实例化默认配置
        default_cfg = AppConfig()
        
        if not CONFIG_FILE.exists():
            return default_cfg

        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 2. 智能合并：将读取的数据覆盖默认值
            # 这样如果 config.json 少了某个新字段，default_cfg 会保留该字段的默认值
            # 过滤掉 AppConfig 中不存在的废弃字段
            valid_keys = default_cfg.__dict__.keys()
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            
            # 更新属性
            for key, value in filtered_data.items():
                setattr(default_cfg, key, value)
                
            return default_cfg
            
        except Exception as e:
            print(f"Error loading settings: {e}, using defaults.")
            # 可以在这里备份一下损坏的配置文件
            shutil.copy(CONFIG_FILE, CONFIG_FILE.with_suffix(".json.bak"))
            return default_cfg

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